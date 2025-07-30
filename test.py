import subprocess

def create_clean_proxy(full_proxy):
    parts = full_proxy.strip().split(':')
    if len(parts) != 4:
        raise ValueError("Invalid proxy format. Must be host:port:user:pass")

    host, port, user, pwd = parts
    full_auth_proxy = f"http://{user}:{pwd}@{host}:{port}"

    # Start proxy-chain in background with auth
    cmd = f"proxy-chain --port 8000 --target {full_auth_proxy}"
    subprocess.Popen(cmd, shell=True)
    
    print("Now use this in DrissionPage:")
    print("http://127.0.0.1:8000")  # This forwards traffic through your authenticated proxy

# Example
proxy_str = "v2.proxyempire.io:5000:r_c7c72217b5-country-de-sid-f3f33j28:9871a9d8a9"
create_clean_proxy(proxy_str)
