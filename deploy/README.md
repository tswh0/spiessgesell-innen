# Test deployment on the Hermes LXC

No Docker daemon here, so the app runs from the venv as user units. Docker stays the
delivery path for the real host (`compose.yml`).

```sh
mkdir -p ~/.config/systemd/user
cp deploy/spiessgesellen.service deploy/spiessgesellen-tunnel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now spiessgesellen spiessgesellen-tunnel
```

- App: `127.0.0.1:8095`, `DATA_DIR=~/work/doner/data-prod`, env in `~/work/doner/.env`.
- URL: quick tunnel. The hostname changes on every tunnel restart:

  ```sh
  journalctl --user -u spiessgesellen-tunnel -n 40 --no-pager | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
  ```

- `doner.twh0.de`: add it to the existing named tunnel `test-twh0` in Zero Trust →
  Networks → Tunnels → `test-twh0` → Public Hostname, service
  `http://127.0.0.1:8095`. That creates the ingress rule and the DNS CNAME. The
  connector token alone cannot add either. Then set `BASE_URL=https://doner.twh0.de`
  (already set) and restart the app.
