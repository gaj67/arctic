from sys import stdin, stdout, stderr
from telnetlib import Telnet
from threading import Thread

class MultiIO:
    """Emulates a simple file-like interface using the commands
    read, readline, and write to access multiple input and/or
    output files.
    """
    def __init__( self, inputs=None, outputs=None ):
        """Optionally configures the input and/or output files:

          * inputs  - an iterator over input files.
          * outputs - an iterator over output files.

        Each of the outputs, if specified, has the same text written to it.
        Each of the inputs, if specified, is read in turn until the end is reached,
        whereupon the next input file is read.
        """
        self.inputs = inputs or [ ]
        self.outputs = outputs or [ ]
        self.index = 0

    def write( self, s ):
        """Writes the given text to all outputs.
        """
        for out in self.outputs:
            out.write( s )

    def read( self, *args ):
        """Reads from the current input, or returns an exception if
        there is no more input.
        """
        while self.index < len( self.inputs ):
            try:
                return self.inputs[ self.index ].read( *args )
            except:
                self.index += 1
        raise IOError, "No more input!"

    def readln( self ):
        """Reads from the current input, or returns an exception if
        there is no more input.
        """
        while self.index < len( self.inputs ):
            try:
                return self.inputs[ self.index ].readln( )
            except:
                self.index += 1
        raise IOError, "No more input!"

    def close( self ):
        """Attempts to close all inputs and outputs.
        """
        for f in self.inputs:
            try:
                f.close( )
            except:
                pass
        for f in self.outputs:
            try:
                f.close( )
            except:
                pass
    
class Session:
    """Provides access to a telnet session, with the ability to track user
    commands in a recallable history, and to also automatically create
    new commands based on the session output.

    See help( Session.__init__ ) for further details.
    """
    
    # Default control symbols. Don't change these directly, see __init__.
    DEFAULT_SETTINGS = {
        # User-input settings.
        'historyCmdSym'    : '!',    # Shows/uses history command(s).
        'historySizeSym'   : '!#',   # Sets maximum history size.
        'historyStickySym' : '!@',   # Adds command to sticky history.
        'historySticky'    : None,   # Sticky history commands.
        'historyDynamic'   : None,   # Dynamic history commands.
        'historySize'      : 10,     # Maximum dynamic history size.
        'repeatToggleSym'  : '!!',   # Toggles mode to repeat last command.
        'repeatCmdSym'     : '',     # Repeats last user command.
        'repeatCmdMode'    : False,  # Is repeat user command mode active?
        'multiSeparateSym' : ';',    # Multi-command separator on single line.
        'multiRepeatSym'   : ';',    # Repeats last command of multi-command.
        'lineSeparateSym'  : '\n',   # End-of-line in session text.
    }

    def __init__( self, host=None, port=None, session=None,
                  input=stdin, output=stdout, error=stderr, **settings ):
        """Configures a session, but without starting it.

        Parameters that can optionally be changed:
          * host             - The host address.
          * port             - The port number.
          * session          - An already opened session.
          * input            - A file-like object for inputting user commands.
          * output           - A file-like object for outputting session text.
          * error            - A file-like object for outputting messages.

        User-input symbols that can optionally be changed:
          * historyCmdSym    - Symbol indicating history command.
          * historyStickySym - Symbol to add command to sticky history.
          * historySizeSym   - Symbol to set maximum dynamic history size.
          * repeatToggleSym  - Toggles mode to repeat last user command.
          * repeatCmdSym     - Repeats last user command.
          * multiSeparateSym - Separator between multi-commands on single line.
          * multiRepeatSym   - Repeat last command of multi-command.
          * lineSeparateSym  - End-of-line in session text.

        Settings that can optionally be changed:
          * historySticky    - Modifiable list of sticky commands.
          * historyDynamic   - Modifiable list of dynamic commands.
          * historySize      - Maximum dynamic history size.
          * repeatCmdMode    - Boolean: Is repeat command mode active?
        """
        self.host = host
        self.port = port
        self.session = session
        self.input = input
        self.output = output
        self.error = error
        self.settings = _settings = dict( Session.DEFAULT_SETTINGS )
        _settings.update( settings )
        if _settings[ 'historySticky' ] is None:
            _settings[ 'historySticky' ] = [ ]
        if _settings[ 'historyDynamic' ] is None:
            _settings[ 'historyDynamic' ] = [ ]

    def start( self ):
        if self.session is None:
            self.session = Telnet( self.host, self.port )
        self.inTask = tin = Thread( name="fromUser", target=self.fromUser )
        self.outTask = tout = Thread( name="toUser", target=self.toUser )
        tout.start( )
        tin.start( )

    def join( self ):
        self.inTask.join( )
        self.outTask.join( )

    ######################################################################
    def fromUser( self ):
        """Processes user input and sends the resulting commands to the
        session.
        """
        self.executeCommands( self.consumeInput( ).next )

    def toUser( self ):
        """Processes session output and sends the resulting commands
        to the session.
        """
        self.executeCommands( self.consumeOutput( ).next )

    def executeCommands( self, func ):
        """
        Repeatedly obtains a command from the function func(), analyses it with
        the function analyse() and sends the result to the telnet session.
        
        Inputs:
          * func    - a function with no arguments which returns a command line
                      string on every invocation, or raises an exception.
        """
        session = self.session.write
        sep = self.settings[ 'multiSeparateSym' ]
        repeat = self.settings[ 'multiRepeatSym' ]
        last_cmd = ''
        for cmd, flag in splitText( func, sep ):
            if repeat != sep and cmd == repeat:
                cmd = last_cmd
            elif repeat == sep and not cmd and flag:
                cmd = last_cmd
            else:
                last_cmd = cmd

            new_cmd = self.analyse( cmd )

            try:
                session( new_cmd )
                session( '\n' )
            except:
                break

    def consumeInput( self ):
        """Each user input line is processed and a command line is yielded.
        
        In the case where the repeat mode is set and the command line
        matches the repeat string, the previous command line is returned.
        
        The repeat mode is off by default, but can be toggled if the toggle
        symbol is valid and is matched by the command line.
        """
        # Handle IO.
        if self.input is None:
            def func( ):
                raise ValueError
        else:
            def func( ):
                s = self.input.readline( )
                if s == '': raise ValueError
                return s.strip( )
        if self.error is not None:
            def err( s ):
                self.error.write( s )
                self.error.flush( )
        else:
            def err( s ): pass

        # Handle settings.
        settings = self.settings
        # Symbols.
        Toggle = settings[ 'repeatToggleSym' ]
        Repeat = settings[ 'repeatCmdSym' ]
        Resize = settings[ 'historySizeSym' ]
        Sticky = settings[ 'historyStickySym' ]
        History = settings[ 'historyCmdSym' ]
        # Status.
        repeating = settings[ 'repeatCmdMode' ]
        max_size = settings[ 'historySize' ]
        sticky = settings[ 'historySticky' ]
        dynamic = settings[ 'historyDynamic' ]
        last_cmd = ''
        
        ################################################
        # Process user commands.
        while True:
            try:
                cmd = func( )
            except:
                err( "Input ended!\n" )
                break
            if cmd == Toggle:
                # Toggle mode to repeat last user command.
                settings[ 'repeatCmdMode' ] = repeating = not repeating
                err( "# Input repeat mode switched to: %s\n" % str( repeating ) )
            elif repeating and cmd == Repeat:
                # Repeat last user command.
                yield last_cmd
            elif cmd == History:
                # Show command history.
                s = len( sticky ); n = s + len( dynamic )
                err( "# History:\n" )
                for i, cmd in enumerate( sticky ):
                    err( "  *[s] %d (%d): %s\n" % ( i+1, i-n, cmd ) )
                for i, cmd in enumerate( dynamic ):
                    err( "  *[d] %d (%d): %s\n" % ( s+i+1, s+i-n, cmd ) )
            elif cmd.startswith( Resize ):
                # Resize dynamic history.
                n = getint( cmd[ len( Resize ): ] )
                if n < 0:
                    err( "# Dynamic history size out of range!\n" )
                    continue
                settings[ 'historySize' ] = max_size = n
                while len( dynamic ) > max_size: dynamic.pop( 0 )
                err( "# Resized dynamic history to maximum of %d commands!\n" % n )
            elif cmd.startswith( Sticky ):
                # Add user command to sticky history.
                sticky.append( cmd[ len( Sticky ): ] )
                err( "# Stored sticky history command!\n" )
            elif cmd.startswith( History ):
                # Recall history command, with lookup number.
                i = getint( cmd[ len( History ): ] )
                s = len( sticky ); n = s + len( dynamic )
                if i is None or i == 0 or abs( i ) > n:
                    err( "# Dynamic history lookup number out of range!\n" )
                    continue
                i = i + n if i < 0 else i - 1
                if i < s: last_cmd = sticky[ i ]
                else: last_cmd = dynamic[ i - s ]
                yield last_cmd
            else: 
                # Handle user command.
                if not dynamic or cmd != dynamic[ -1 ]:
                    dynamic.append( cmd )
                    while len( dynamic ) > max_size: dynamic.pop( 0 )
                last_cmd = cmd
                yield cmd

    def consumeOutput( self ):
        """Each chunk of output obtained from the session is processed and
        the resulting command lines are yielded.
        """
        out = self.output
        func = self.session.read_some
        sep = self.settings[ 'lineSeparateSym' ]
        line = ''
        complete = True
        for chunk, eol in splitText( func, sep ):
            if out is not None:
                out.write( chunk )
                if eol: out.write( '\n' )
                out.flush( )
            if complete:
                line = chunk
            else:
                line += chunk
            complete = eol
            for cmd in self.process( line, complete ):
                yield cmd

    ######################################################################
    def analyse( self, cmd ):
        """Analyses the given command string and returns a processed
        command string.
        """
        return cmd

    def process( self, line, complete ):
        """Processes the given line, and line-completion Boolean flag,
        and returns a generator yielding command line strings.
        """
        if False:
            yield None

##########################################################################
def splitText( func, sep ):
    """Repeatedly obtains a line of text from func(), separates it into
    multiple chunks using the separator sep, and yields the chunk and
    a Boolean flag indicating whether (True) or not (False) the chunk
    ended with the separator (which is removed if so).
    
    Inputs:
      * func - a function with no arguments which returns a command line
               string on every invocation, or raises an exception.
      * sep  - a separator string for breaking the input line into chunks.
    """
    while True:
        try:
            line = func( )
        except:
            break
        while True:
            first, _sep, line = line.partition( sep )
            yield first, bool( _sep )
            if not line: break
            # Note: A line containing just sep results in '', True.
            # An empty line results in '', False.

def getint( s ):
    try:
        return int( s )
    except:
        return None

##########################################################################
if __name__ == "__main__":

    def go( host, port, output=None ):
        s = Session( host=host, port=port, output=output )
        s.start( )
        s.join( )

    from sys import argv, stdout
    if len( argv ) < 3:
        print "Usage: %s <host> <port>" % argv[ 0 ]
    else:
        #fout = file( "session.out", "wt" )
        #output = MultiIO( outputs=[ stdout, fout ] )
        output = stdout
        go( argv[ 1 ], argv[ 2 ], output )
        output.close( )
    