from flask import Flask, jsonify
import platform, subprocess, re, socket, shlex, time

app = Flask(__name__)

def run_cmd(cmd, timeout=4):
    try:
        if isinstance(cmd, (list, tuple)):
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=timeout)
        else:
            out = subprocess.check_output(shlex.split(cmd), stderr=subprocess.DEVNULL, timeout=timeout)
        return out.decode(errors='ignore')
    except Exception:
        return ""

def get_gateway_ip():
    system = platform.system().lower()
    if system in ("linux", "darwin"):
        out = run_cmd("ip route get 1.1.1.1")
        m = re.search(r"via\s+([\d.]+)", out)
        if m: return m.group(1)
        out = run_cmd("ip route show default")
        m = re.search(r"default via\s+([\d.]+)", out)
        if m: return m.group(1)
        out = run_cmd("netstat -rn")
        m = re.search(r"default\s+([\d.]+)\s", out)
        if m: return m.group(1)
        out = run_cmd("route -n")
        m = re.search(r"0\.0\.0\.0\s+([\d.]+)\s", out)
        if m: return m.group(1)
        return None

    elif system == "windows":
        out = run_cmd("route print -4")
        m = re.search(r"0\.0\.0\.0\s+0\.0\.0\.0\s+([\d.]+)\s+([\d.]+)\s+\d+", out)
        if m: return m.group(1)
        out = run_cmd("ipconfig")
        matches = re.findall(r"Default Gateway[^\r\n:]*:\s*([\d.]+)", out)
        for gw in matches:
            if gw and gw != "0.0.0.0":
                return gw
        try:
            host_ip = socket.gethostbyname(socket.gethostname())
            if host_ip and not host_ip.startswith("127."):
                parts = host_ip.split(".")
                parts[-1] = "1"
                return ".".join(parts)
        except Exception:
            pass
        return None
    else:
        return None

def get_arp_mac(ip):
    if not ip: return None
    system = platform.system().lower()
    if system in ("linux", "darwin"):
        out = run_cmd(f"ip neigh show {ip}")
        m = re.search(r"lladdr\s+([0-9a-f:]{17}|[0-9a-f:]{14}|[0-9a-f:]{12})", out.lower())
        if m: return m.group(1)
        out = run_cmd(f"arp -n {ip}")
        m = re.search(r"([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}", out.lower())
        if m: return m.group(0)
        out = run_cmd("arp -a")
        m = re.search(re.escape(ip) + r".*?([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}", out.lower(), re.DOTALL)
        if m: return m.group(0)
        return None
    elif system == "windows":
        out = run_cmd("arp -a")
        pattern = re.compile(rf"^\s*{re.escape(ip)}\s+([0-9a-fA-F\-]{{17}})\s", re.MULTILINE)
        m = pattern.search(out)
        if m:
            mac = m.group(1).replace("-", ":").lower()
            return mac
        m2 = re.search(re.escape(ip) + r".*?([0-9a-fA-F\-]{17})", out, re.DOTALL)
        if m2:
            mac = m2.group(1).replace("-", ":").lower()
            return mac
        return None
    else:
        return None

def ping_once(ip):
    if not ip: return False
    system = platform.system().lower()
    cmd = ["ping", "-n", "1", ip] if system == "windows" else ["ping", "-c", "1", "-W", "1", ip]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
        return True
    except Exception:
        return False

@app.route('/api/gateway', methods=['GET'])
def api_gateway():
    gw = get_gateway_ip()
    if not gw:
        return jsonify({
            "status": "error",
            "message": "Could not detect default gateway. Try running as admin/sudo."
        }), 500

    mac = get_arp_mac(gw)
    if not mac:
        ping_once(gw)
        time.sleep(1)
        mac = get_arp_mac(gw)

    return jsonify({
        "status": "success" if mac else "partial",
        "gateway_ip": gw,
        "gateway_mac": mac or "Not found (try ping first)",
        "system": platform.system()
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
