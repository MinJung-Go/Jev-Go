"""Password-protected network access to the running local Jev demo."""
import argparse
import base64
import hmac
import http.client
import secrets
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Preview(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def error(self,code,message):
        data=message.encode()
        self.send_response(code)
        if code==401:self.send_header('WWW-Authenticate','Basic realm="Jev test", charset="UTF-8"')
        self.send_header('Content-Type','text/plain; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers();self.wfile.write(data)
    def forward(self):
        if not hmac.compare_digest(self.headers.get('Authorization',''),self.server.authorization):
            return self.error(401,'Login required')
        origin=self.headers.get('Origin')
        if origin and origin!=getattr(self.server,'public_scheme','http')+'://'+self.headers.get('Host',''):
            return self.error(403,'Origin rejected')
        if self.path not in {'/','/style.css','/app.js','/api/config','/api/state','/api/decision','/api/payload'}:
            return self.error(404,'Not found')
        if self.headers.get('Transfer-Encoding'):return self.error(400,'Unsupported transfer encoding')
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<=size<=20000:return self.error(413,'Request too large')
        except ValueError:return self.error(400,'Invalid length')
        data=self.rfile.read(size) if size else None
        conn=http.client.HTTPConnection('127.0.0.1',self.server.upstream,timeout=75)
        try:
            conn.request(self.command,self.path,body=data,headers={'Content-Type':self.headers.get('Content-Type','application/json')})
            response=conn.getresponse();data=response.read()
            self.send_response(response.status)
            self.send_header('Content-Type',response.getheader('Content-Type','application/json'))
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers();self.wfile.write(data)
        except (OSError,http.client.HTTPException):self.error(502,'Upstream unavailable')
        finally:conn.close()
    do_GET=forward
    do_POST=forward

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--upstream',type=int,default=8765)
    parser.add_argument('--tls-cert');parser.add_argument('--tls-key')
    args=parser.parse_args()
    if bool(args.tls_cert)!=bool(args.tls_key):parser.error('TLS certificate and key must be supplied together')
    password=secrets.token_urlsafe(18)
    httpd=ThreadingHTTPServer(('0.0.0.0',args.port),Preview)
    httpd.authorization='Basic '+base64.b64encode(('jev:'+password).encode()).decode()
    httpd.upstream=args.upstream
    httpd.public_scheme='https' if args.tls_cert else 'http'
    if args.tls_cert:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.tls_cert,args.tls_key)
        httpd.socket=context.wrap_socket(httpd.socket,server_side=True)
    print(f'Listening on 0.0.0.0:{args.port}; user=jev password={password}',flush=True)
    httpd.serve_forever()
