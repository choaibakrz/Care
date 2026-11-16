"""Mini app locale pour tester best.pt : glisse une image dans la page, le modèle renvoie l'image annotée.
Lancer : python models/test_app.py   (ouvre http://localhost:8765). Rien ne sort du PC."""
import base64, io, json, webbrowser, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image
from ultralytics import YOLO

PORT = 8765
MODEL = YOLO(str(Path(__file__).with_name('best.pt')))
MAX_BYTES = 20 * 1024 * 1024

PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Test YOLO</title>
<style>
body{font-family:system-ui,sans-serif;background:#0f1416;color:#e8eef0;margin:0;padding:24px;display:grid;gap:16px;justify-items:center}
h1{margin:0;font-size:22px} #drop{width:min(640px,100%);border:2px dashed #4fe0b5;border-radius:14px;padding:40px;text-align:center;cursor:pointer}
#drop.over{background:#4fe0b522} img{max-width:min(900px,100%);border-radius:10px}
label{font-size:14px} table{border-collapse:collapse;font-size:15px} td{padding:6px 14px;border-bottom:1px solid #2a3336}
.bad{color:#ff8f7a}
</style></head><body>
<h1>Test du modèle best.pt</h1>
<div id="drop">Glisse une image ici, colle-la (Ctrl+V) ou clique pour choisir</div>
<input id="file" type="file" accept="image/*" hidden>
<label>Seuil de confiance : <input id="conf" type="range" min="5" max="90" value="25"> <b id="cv">25</b> %</label>
<div id="out"></div>
<script>
const drop=document.getElementById('drop'),file=document.getElementById('file'),out=document.getElementById('out'),conf=document.getElementById('conf');
let last=null;
conf.oninput=()=>{document.getElementById('cv').textContent=conf.value};
conf.onchange=()=>{if(last)send(last)};
drop.onclick=()=>file.click();
file.onchange=()=>file.files[0]&&send(file.files[0]);
drop.ondragover=e=>{e.preventDefault();drop.classList.add('over')};
drop.ondragleave=()=>drop.classList.remove('over');
drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');e.dataTransfer.files[0]&&send(e.dataTransfer.files[0])};
document.onpaste=e=>{const f=[...e.clipboardData.files][0];if(f)send(f)};
async function send(f){last=f;out.textContent='Analyse…';
 try{const r=await fetch('/detect?conf='+conf.value/100,{method:'POST',body:f});const d=await r.json();
  if(d.error){out.innerHTML='<p class="bad">'+d.error+'</p>';return}
  const rows=d.detections.map(x=>'<tr><td>'+x.label+'</td><td>'+x.conf+' %</td></tr>').join('')||'<tr><td class="bad">Aucun objet détecté</td></tr>';
  out.innerHTML='<img src="data:image/jpeg;base64,'+d.image+'"><table>'+rows+'</table><p>'+d.ms+' ms</p>';
 }catch(err){out.innerHTML='<p class="bad">Erreur : '+err+'</p>'}}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200, PAGE.encode(), 'text/html; charset=utf-8')

    def do_POST(self):
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= MAX_BYTES:
                raise ValueError('Image vide ou trop lourde (max 20 Mo).')
            conf = float(self.path.split('conf=')[-1]) if 'conf=' in self.path else 0.25
            img = Image.open(io.BytesIO(self.rfile.read(size))).convert('RGB')
            result = MODEL(img, conf=max(0.01, min(conf, 0.99)), verbose=False)[0]
            annotated = Image.fromarray(result.plot()[..., ::-1])
            buf = io.BytesIO()
            annotated.save(buf, 'JPEG', quality=90)
            dets = [{'label': result.names[int(b.cls)], 'conf': round(float(b.conf) * 100, 1)} for b in result.boxes]
            body = {'image': base64.b64encode(buf.getvalue()).decode(), 'detections': dets,
                    'ms': round(sum(result.speed.values()))}
            self._send(200, json.dumps(body).encode(), 'application/json')
        except Exception as exc:  # message lisible dans la page
            self._send(400, json.dumps({'error': f'Image illisible : {exc}'}).encode(), 'application/json')


if __name__ == '__main__':
    url = f'http://localhost:{PORT}'
    print(f'App de test ouverte sur {url}  (Ctrl+C pour arrêter)')
    threading.Timer(1, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
