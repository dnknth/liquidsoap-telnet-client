#!/usr/bin/env python3

import argparse, cmd, socket, time, os.path

class Connection:
    ''' Reconnecting telnet connection to Liquidsoap.
        Liquidsoap will hang up on us after ~1 minute,
        so we open a new socket connection when needed.
    '''
    
    END_MARKER = b'\r\nEND\r\n'
    BUFSIZE = 4096
    QUIT_CMD = 'quit'
    QUIT_MARKER = b'Bye!\r\n'

    def __init__( self, socket_addr):
        self.socket_addr = socket_addr
        self.socket = None

    def __enter__( self):
        if self.socket is None: self._connect()
        return self

    def _connect( self):
        'Connect to Liquidsoap'

        if ':' in self.socket_addr:
            host, port = self.socket_addr.split( ':', 1)
            self.socket = socket.socket( socket.AF_INET)
            self.socket.connect( (host, int( port)))
        else:
            self.socket = socket.socket( socket.AF_UNIX)
            self.socket.connect( self.socket_addr)

        # self.socket.setblocking( False)
        self.socket.settimeout( 0.1)
        return self
        
    def send( self, command, marker=END_MARKER):
        'Send a command, return the response text'

        if self.socket is None: self._connect()

        request = b'%s\n' % command.strip().encode()
        total = 0
        while total < len( request):
            sent = self.socket.send( request[ total:])
            total += sent
            if sent == 0:
                self.socket = None
                raise OSError( 'Connection lost')

        reply = bytearray()
        while not reply.endswith( marker):
            chunk = self.socket.recv( self.BUFSIZE)
            if not chunk:
                self.socket = None
                raise OSError( 'Connection lost')
            reply += chunk
        return reply.decode()[:-len( marker)]
    
    def __exit__( self, type, value, traceback):
        'Close the connection'

        if self.socket is not None:
            try:
                self.send( self.QUIT_CMD, self.QUIT_MARKER)
            except OSError:
                pass
            self.socket.close()


class Console( cmd.Cmd):
    'Simple interactive command processor'

    prompt = '\033[01;33m>\033[00m '
    intro = "\033[33mInteractive Liquidsoap console, type '?' for help.\033[00m"
    history_path = os.path.expanduser( '~/.liquidsoap_history')

    def __init__( self, connection):
        super().__init__()
        self.connection = connection
            
    def _send( self, line):
        'Send a command, reconnect on error'
        try:
            return self.connection.send( line)
        except OSError:
            return self.connection.send( line)

    def default( self, line):
        'Send a command, print the respone'
        print( self._send( line))

    def emptyline( self): pass
        
    def do_help( self, arg):
        self.default( 'help %s' % arg)

    def do_exit( self, arg): return True

    def do_quit( self, arg): return True

    def do_EOF( self, arg):
        print()
        return True

    def completenames( self, text, *ignored):
        'Get command completions from Liquidsoap'

        names = super().completenames( text, *ignored)
        for line in self._send( 'help').split( '\n'):
            if line.startswith( '| ' + text):
                names.append( line.split()[1])
        return names

    def preloop( self):
        'Read the history file if possible'
        try:
            import readline
            if os.path.isfile( self.history_path):
                readline.read_history_file( self.history_path)
        except ImportError:
            pass

    def postloop( self):
        'Save the command history'
        try:
            import readline
            readline.write_history_file( self.history_path)
        except ImportError:
            pass


if __name__ == '__main__':

    parser = argparse.ArgumentParser( description='Telnet client for Liquidsoap')
    parser.add_argument( '-s', '--socket', default='localhost:1234',
        help='Socket address as host:port or Unix domain socket path')
    parser.add_argument( 'infile', nargs='*', type=argparse.FileType(),
        help='File with lquidsoap commands')

    args = parser.parse_args()

    if not args.infile: # No arguments --> Enter interactive mode
        try:
            with Connection( args.socket) as con:
                Console( con).cmdloop()
        except KeyboardInterrupt:
            print( 'Interrupted.')

    for f in args.infile:
        with Connection( args.socket) as con:
            for cmd in f: print( con.send( cmd))
