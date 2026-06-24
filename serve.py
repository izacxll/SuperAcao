#!/usr/bin/env python3
# =============================================================================
# serve.py  ·  servidor local para testar o SuperAcao SP sem dor de CORS
# -----------------------------------------------------------------------------
# Serve os arquivos desta pasta E faz proxy da API do Trampolim na MESMA
# origem da pagina. O navegador so fala com este servidor (sem CORS); este
# servidor busca na API real (servidor-pra-servidor nao tem CORS).
#
# USO:
#   1) no index.html:  TRAMPOLIM_BASE = "/trampolim"  e  TRAMPOLIM_CORS_PROXY = false
#      (ja vem assim)
#   2) nesta pasta:    python3 serve.py
#   3) abra:           http://localhost:8080
#
# So precisa de Python 3 (biblioteca padrao, sem pip install).
# Opcional: PORTA=9000 python3 serve.py   /   TRAMPOLIM_ALVO=https://... python3 serve.py
# =============================================================================
import os
import ssl
import glob
import urllib.request
import urllib.error
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORTA   = int(os.environ.get("PORTA", "8080"))
PREFIXO = "/trampolim"
ALVO    = os.environ.get("TRAMPOLIM_ALVO", "https://www.trampolim.sp.gov.br").rstrip("/")
PAGINA  = os.environ.get("PAGINA", "").strip()   # arquivo servido em "/" (vazio = index.html padrao)

# Contexto SSL para falar com a API (HTTPS). Em Mac, o Python (sobretudo no
# Anaconda) as vezes nao acha a lista de certificados e a verificacao falha
# com "CERTIFICATE_VERIFY_FAILED" -> resultava em 502. Tentamos o bundle do
# certifi; se nao existir, o padrao do sistema.
try:
    import certifi
    CTX_SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX_SSL = ssl.create_default_context()
# INSEGURO=1 desliga a verificacao de certificado (ultimo recurso, SO p/ teste local).
if os.environ.get("INSEGURO") == "1":
    CTX_SSL = ssl._create_unverified_context()


class Handler(SimpleHTTPRequestHandler):

    def do_GET(self):
        # 1) PROXY DA API:  /trampolim/...  ->  ALVO/...
        if self.path.startswith(PREFIXO):
            destino = ALVO + self.path[len(PREFIXO):]   # mantem ? & + %.. como vieram
            req = urllib.request.Request(destino, headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",          # evita gzip (simplifica o repasse)
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            })
            try:
                with self._abrir(req) as up:
                    corpo = up.read()
                    self._responder(up.status, up.headers, corpo)
                    print("[proxy]", up.status, destino[:110])
            except urllib.error.HTTPError as e:          # a API respondeu com erro (4xx/5xx)
                corpo = e.read()
                self._responder(e.code, e.headers, corpo)
                print("[proxy] HTTP", e.code, destino[:110])
            except Exception as e:                       # falha de rede/timeout
                msg = ('{"erro":"falha no proxy","detalhe":%r}' % str(e)).encode("utf-8")
                self._responder(502, {}, msg, "application/json")
                print("[proxy] erro:", e)
            return
        # 2) ARQUIVOS ESTATICOS (a partir da pasta atual)
        if PAGINA and self.path == "/":
            self.path = "/" + PAGINA          # abre o arquivo escolhido em vez do index.html padrao
        return super().do_GET()

    def _abrir(self, req):
        # abre a URL na API; se falhar por SSL (cert), tenta UMA vez sem verificar
        try:
            return urllib.request.urlopen(req, timeout=20, context=CTX_SSL)
        except urllib.error.HTTPError:
            raise                              # erro HTTP (4xx/5xx) -> tratado no do_GET
        except urllib.error.URLError as e:
            motivo = getattr(e, "reason", None)
            if isinstance(motivo, ssl.SSLError) or "CERTIFIC" in str(motivo).upper() or "SSL" in str(motivo).upper():
                print("[proxy] SSL falhou; repetindo sem verificar certificado (so teste local)")
                return urllib.request.urlopen(req, timeout=20, context=ssl._create_unverified_context())
            raise

    def _responder(self, status, headers, corpo, ct_padrao="application/json"):
        try:
            self.send_response(status)
            self.send_header("Content-Type", (headers.get("Content-Type") if hasattr(headers, "get") else None) or ct_padrao)
            ce = headers.get("Content-Encoding") if hasattr(headers, "get") else None
            if ce:
                self.send_header("Content-Encoding", ce)  # repassa se a API insistir em comprimir
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        except BrokenPipeError:
            pass

    def log_message(self, *args):   # silencia o log de cada arquivo estatico
        pass


if __name__ == "__main__":
    ThreadingHTTPServer.allow_reuse_address = True
    htmls = sorted(glob.glob("*.html"))
    with ThreadingHTTPServer(("", PORTA), Handler) as httpd:
        print("Servidor no ar:  http://localhost:%d" % PORTA)
        print("Pasta servida:   %s" % os.getcwd())
        print("HTMLs na pasta:  %s" % (", ".join(htmls) if htmls else "(NENHUM .html aqui!)"))
        print("Abrindo em / :   %s" % (PAGINA if PAGINA else "index.html (padrao)"))
        print("Proxy da API:    %s/...  ->  %s/..." % (PREFIXO, ALVO))
        print("(Ctrl+C para parar)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nencerrando...")
