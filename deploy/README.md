# Deploying to an Oracle Cloud "Always Free" VM

One small VM runs the whole stack with Docker Compose (`docker-compose.prod.yml`):

```
Internet ──► Caddy  :80/:443   HTTPS (Let's Encrypt), serves the built frontend,
               │               proxies /api/* to the backend
               ▼
           backend :8000       FastAPI (internal network only)
               ▼
           db      :5432       PostgreSQL 16 (internal network only, volume pgdata)
```

Frontend and API share one HTTPS origin, so the `SameSite=Lax` refresh cookie works without any
cross-site setup. The API docs (`/docs`, `/openapi.json`) are not exposed publicly.

You need: an Oracle Cloud account (a card is required for verification), an SSH key pair, and a
domain name — or use a free `sslip.io` hostname (step 3).

> Free-tier terms change. In June 2026 Oracle reduced the Always Free Ampere (ARM) allowance to
> **2 OCPUs and 12 GB RAM** in total. Check the "Always Free-eligible" label in the console before
> creating anything.

## 1. Create the VM

1. Console → **Compute → Instances → Create instance**.
2. **Image:** Canonical Ubuntu 24.04.
3. **Shape:** Ampere → `VM.Standard.A1.Flex`, **2 OCPUs, 12 GB memory** (the free maximum).
4. **Networking:** a VCN with a public subnet, **assign a public IPv4 address**.
5. **SSH keys:** paste your public key.
6. Create. If you get *Out of capacity*, pick another availability domain or retry later
   (ARM capacity in popular regions is often exhausted for a while).

Note the public IP. It stays the same while the instance exists; if you terminate and recreate the
instance, update DNS with the new address.

## 2. Open ports 80 and 443

Two firewalls are in the way, and both must allow the traffic.

**Cloud firewall:** Networking → Virtual cloud networks → *your VCN* → *public subnet* →
*security list* → **Add ingress rules**, source `0.0.0.0/0`:

| Protocol | Destination port |
| --- | --- |
| TCP | 80 |
| TCP | 443 |
| UDP | 443 (HTTP/3, optional) |

**Host firewall:** Oracle's Ubuntu images ship iptables rules that reject everything except SSH.
SSH in (`ssh ubuntu@<public-ip>`) and run this **before installing Docker**, so the saved rule set
does not capture Docker's own rules:

```bash
sudo iptables -I INPUT -p tcp -m multiport --dports 80,443 -m conntrack --ctstate NEW -j ACCEPT
```

```bash
sudo iptables -I INPUT -p udp --dport 443 -m conntrack --ctstate NEW -j ACCEPT
```

```bash
sudo netfilter-persistent save
```

## 3. Point a hostname at the VM

Create a DNS **A record** for your domain (e.g. `library.example.com`) pointing to the public IP,
then check it from your machine:

```bash
dig +short library.example.com
```

No domain yet? Use `<ip-with-dashes>.sslip.io`, e.g. `203-0-113-10.sslip.io` for `203.0.113.10`.
It resolves to that IP without any setup and Caddy can get a certificate for it.

Caddy requests the certificate on first start, so DNS must already point to the VM by then.

## 4. Install Docker and Git

```bash
sudo apt-get update && sudo apt-get install -y git
```

```bash
curl -fsSL https://get.docker.com | sudo sh
```

```bash
sudo usermod -aG docker "$USER"
```

Log out and back in (for the group change), then check:

```bash
docker compose version
```

(The script is Docker's official convenience installer; the apt-repository method from
docs.docker.com works too.)

## 5. Get the code and configure

```bash
git clone https://github.com/igorpertsev/librarium.git && cd librarium
```

For a private repository use a read-only deploy key or an HTTPS access token.

```bash
cp deploy/.env.production.example .env && chmod 600 .env
```

Generate the two secrets and put them into `.env` together with `DOMAIN` and `ACME_EMAIL`:

```bash
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32)); print('JWT_SECRET_KEY=' + secrets.token_urlsafe(64))"
```

```bash
nano .env
```

Keep `.env` safe: losing `POSTGRES_PASSWORD` locks you out of the existing database volume.
Changing `JWT_SECRET_KEY` later only signs everybody out.

## 6. Start the stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The first build takes a few minutes (frontend type check and build, backend image). Then:

```bash
docker compose -f docker-compose.prod.yml ps
```

`db`, `backend` and `web` should be running (`migrate` exits with code 0 after applying migrations).

```bash
curl https://library.example.com/api/v1/health
```

Expected: `{"status":"ok","database":"ok"}`. Open `https://library.example.com` in a browser.

## 7. Create the administrator

Set `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` (at least 12 characters) in `.env`, then:

```bash
docker compose -f docker-compose.prod.yml run --rm backend python -m app.cli seed
```

Afterwards remove `SEED_ADMIN_PASSWORD` from `.env`. Demo books are refused in production on
purpose; add real books in the admin portal. Customers register themselves on the site.

## 8. Backups

`deploy/backup.sh` writes a compressed `pg_dump` to `~/librarium-backups` (override with
`BACKUP_DIR`) and deletes dumps older than 14 days (`KEEP_DAYS`). Run it once by hand — this also
creates the directory — then schedule it:

```bash
deploy/backup.sh
```

```bash
crontab -e
```

```
0 3 * * * /home/ubuntu/librarium/deploy/backup.sh >> /home/ubuntu/librarium-backups/backup.log 2>&1
```

Dumps on the VM do not survive losing the VM. Copy them elsewhere regularly, for example to your
own machine:

```bash
scp 'ubuntu@<public-ip>:librarium-backups/*.dump' ./librarium-backups/
```

or to object storage with `rclone`.

**Restore** a dump (replaces the current data):

```bash
docker compose -f docker-compose.prod.yml stop backend web
```

```bash
docker compose -f docker-compose.prod.yml exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < ~/librarium-backups/librarium-YYYYMMDDTHHMMSSZ.dump
```

```bash
docker compose -f docker-compose.prod.yml start backend web
```

## 9. Updating

```bash
cd ~/librarium && deploy/backup.sh && git pull
```

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

```bash
docker image prune -f
```

The `migrate` service applies new Alembic migrations before the backend restarts. Expect a few
seconds of downtime while the single backend container is replaced.

## Everyday commands

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=100 backend
```

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=100 web
```

```bash
docker compose -f docker-compose.prod.yml restart backend
```

```bash
docker compose -f docker-compose.prod.yml exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Container logs are rotated (5 × 10 MB per container), so they do not fill the disk.

## Security notes

- Only ports 22, 80 and 443 are open; PostgreSQL and the backend are reachable only inside Docker.
- `ENVIRONMENT=production` is enforced: the backend refuses to start with a weak `JWT_SECRET_KEY`,
  and cookies are `Secure` and `HttpOnly`.
- Caddy sets HSTS and basic security headers and ignores client-supplied `X-Forwarded-For`, so the
  IP addresses stored with sessions cannot be spoofed.
- Keep the OS patched (`sudo apt-get update && sudo apt-get upgrade`; Ubuntu installs security
  updates automatically via unattended-upgrades) and use SSH keys only.
- Not included yet: login rate limiting and a Content-Security-Policy header.

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| `required variable ... is missing a value` | `.env` is missing or incomplete next to `docker-compose.prod.yml`. |
| Site unreachable, or no certificate | DNS not pointing to the VM yet, or port 80/443 closed in the security list or iptables (step 2). Check `logs web`. |
| `502 Bad Gateway` | Backend not running; check `logs backend`. In production it refuses to start with an invalid configuration and prints why. |
| Logged out after every reload | The site was opened by IP or another hostname instead of `DOMAIN`. |
| *Out of capacity* when creating the VM | Retry later or choose another availability domain. |
| VM stopped or reclaimed by Oracle | Oracle may reclaim idle Always Free instances; check their current policy and keep off-VM backups. |
