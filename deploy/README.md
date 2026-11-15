# Test deployment on the Hermes LXC

No Docker daemon here, so the app runs from the venv as user units. Docker stays the
delivery path for the real host (`compose.yaml`).

```sh
mkdir -p ~/.config/systemd/user
cp deploy/spiessgesell-innen.service deploy/spiessgesell-innen-tunnel.service ~/.config/systemd/user
systemctl --user daemon-reload
systemctl --user enable --now spiessgesell-innen spiessgesell-innen-tunnel
```

Backups run inside the app at 03:15 (`BACKUP_ENABLED=1` in the service unit). To make one by hand:

```sh
.venv/bin/python scripts/backup.py
```

- App: `127.0.0.1:8095`, `DATA_DIR=~/work/doner/data-prod`, env in `~/work/doner/.env`.
- URL: quick tunnel. The hostname changes on every tunnel restart:

  ```sh
  journalctl --user -u spiessgesell-innen-tunnel -n 40 --no-pager | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
  ```

- `doner.twh0.de`: add it to the existing named tunnel `test-twh0` in Zero Trust →
  Networks → Tunnels → `test-twh0` → Public Hostname, service
  `http://127.0.0.1:8095`. That creates the ingress rule and the DNS CNAME. The
  connector token alone cannot add either. Then set `BASE_URL=https://doner.twh0.de`
  (already set) and restart the app.
