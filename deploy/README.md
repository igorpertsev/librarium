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

Generate the secrets and put them into `.env` together with `DOMAIN` and `ACME_EMAIL`:

```bash
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32)); print('JWT_SECRET_KEY=' + secrets.token_urlsafe(64)); print('MFA_ENCRYPTION_KEYS=' + secrets.token_urlsafe(32))"
```

```bash
nano .env
```

Keep `.env` safe: losing `POSTGRES_PASSWORD` locks you out of the existing database volume, and
losing `MFA_ENCRYPTION_KEYS` turns two-step sign-in off for everybody who uses it. Changing
`JWT_SECRET_KEY` later only signs everybody out (as long as `MFA_ENCRYPTION_KEYS` is set).

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
`BACKUP_DIR`), next to it an archive of the uploaded book covers (`librarium-media-*.tar.gz`, the
`media` volume), and deletes both after 14 days (`KEEP_DAYS`). To restore covers, unpack the archive
into the volume: `docker compose -f docker-compose.prod.yml exec -T backend tar -xzf - -C /app < librarium-media-….tar.gz`. Run it once by hand — this also
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

Dumps on the VM do not survive losing the VM, so also keep copies elsewhere.

**Off-site copies (rclone).** `backup.sh` uploads every new dump when `RCLONE_REMOTE` is set, and deletes
uploaded dumps older than `REMOTE_KEEP_DAYS` (default 90) there. rclone runs from its Docker image; its
configuration lives in `~/.config/rclone/rclone.conf`. Oracle's Always Free tier includes 20 GB of Object
Storage, which is plenty:

1. Console → **Storage → Buckets → Create bucket** `librarium-backups` (private, standard tier). Note
   your **namespace** on the bucket page.
2. Profile menu → **User settings → Customer secret keys → Generate secret key**; copy the secret (it is
   shown once) and the access key.
3. On the VM:

   ```bash
   mkdir -p ~/.config/rclone && nano ~/.config/rclone/rclone.conf && chmod 600 ~/.config/rclone/rclone.conf
   ```

   ```ini
   [oci]
   type = s3
   provider = Other
   access_key_id = <access key>
   secret_access_key = <secret>
   region = <region, e.g. eu-frankfurt-1>
   endpoint = https://<namespace>.compat.objectstorage.<region>.oraclecloud.com
   no_check_bucket = true
   ```

4. Test it, then add the variable to the cron line:

   ```bash
   RCLONE_REMOTE=oci:librarium-backups deploy/backup.sh
   ```

   ```
   0 3 * * * RCLONE_REMOTE=oci:librarium-backups /home/ubuntu/librarium/deploy/backup.sh >> /home/ubuntu/librarium-backups/backup.log 2>&1
   ```

Any rclone destination works the same way (Backblaze B2, another server over SFTP, ...). A copy in the same
cloud account survives losing the VM, not losing the account; for that, also pull dumps to your own
machine from time to time:

```bash
scp 'ubuntu@<public-ip>:librarium-backups/*.dump' ./librarium-backups/
```

**Restore drill.** A backup only counts if it restores. `deploy/verify-backup.sh` loads the newest dump
(or the one given) into a throwaway PostgreSQL container without network access, prints the schema
revision and row counts, and exits non-zero if anything fails. Run it once now and then weekly:

```bash
deploy/verify-backup.sh
```

```
0 4 * * 0 /home/ubuntu/librarium/deploy/verify-backup.sh >> /home/ubuntu/librarium-backups/backup.log 2>&1
```

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

## Email notifications (optional)

The `notifier` service emails customers about their orders and due dates. To enable it, put your
mail provider's SMTP settings into `.env` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`,
`SMTP_PASSWORD`, `MAIL_FROM`; port 587 with STARTTLS is the usual choice), then apply them:

```bash
docker compose -f docker-compose.prod.yml up -d
```

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=50 notifier
```

Use a sender address on a domain whose SPF/DKIM records your provider has set up, otherwise
messages tend to end up in spam. Without `SMTP_HOST` nothing is sent.

## Book translations (optional machine translation)

Readers see a book's title and description in their interface language when the book has a
translation. In the book form, **Find translation** suggests one from Wikidata (the official
title of the translated edition) and Wikipedia (the article's first paragraph, credited with a
link). This needs no setup, only outbound HTTPS from the VM to `www.wikidata.org` and
`ru.wikipedia.org` / `en.wikipedia.org` (Oracle's default rules allow it).

With an Anthropic API key, what Wikidata and Wikipedia lack is machine-translated as well and
marked "Machine translation" for the librarian to check. To turn it on, put the key into `.env`:

```bash
nano .env
```

Set `ANTHROPIC_API_KEY=...` (and, if you want another model, `TRANSLATION_MODEL`), then apply it:

```bash
docker compose -f docker-compose.prod.yml up -d
```

To check, open a book without an ISBN in the admin portal and click **Find translation**: the
fields are filled in with a "Machine translation" badge. Each lookup that needs it is one request
billed to your Anthropic account; only book data (title, author, description) is sent. To turn it
off again, empty `ANTHROPIC_API_KEY` and run the same `up -d`.

To translate the books that have no translation yet in one go (results are saved with their
source; look them over in the admin portal afterwards):

```bash
docker compose -f docker-compose.prod.yml run --rm backend python -m app.cli translate-books --to ru --no-machine --limit 50
```

Drop `--no-machine` to fill the gaps with machine translation too (at most one request per book).

## Telegram notifications (optional)

Readers can get the same news as the emails in Telegram. Create a bot: in Telegram, open
@BotFather, send `/newbot`, choose a name and a username ending in `bot`, and copy the token it
gives you. Put both into `.env`:

```bash
nano .env   # TELEGRAM_BOT_TOKEN=123456:ABC…  TELEGRAM_BOT_USERNAME=little_dragon_library_bot
docker compose -f docker-compose.prod.yml up -d
```

The profile then shows **Connect Telegram**. The notifier asks Telegram for new messages every
cycle (no webhook, so no extra port), links the chat when the reader presses Start, and sends each
notification there as well as by email; it works even without SMTP. Messages go to Telegram's
servers. To turn it off, empty both values and run the same `up -d`; linked chats stop getting
messages.

## Covers in S3-compatible storage (optional)

Uploaded covers live in the `media` volume by default. To keep them in a bucket instead (AWS S3,
Cloudflare R2, Backblaze B2, a MinIO or RustFS server…), create the bucket and a key that may read,
write and delete in it, then set in `.env`:

```text
S3_ENDPOINT=https://s3.eu-central-1.amazonaws.com
S3_REGION=eu-central-1
S3_BUCKET=little-dragon-covers
S3_ACCESS_KEY_ID=…
S3_SECRET_ACCESS_KEY=…
```

If the bucket (or a CDN in front of it) is public, put its address in `MEDIA_PUBLIC_URL`: browsers
are then redirected there and load covers straight from it. Otherwise the backend streams them from
the private bucket. Restart and copy the covers you already have:

```bash
docker compose -f docker-compose.prod.yml up -d
```

```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.cli media-to-s3
```

Cover URLs do not change (`/media/covers/…`), so nothing else needs updating. `deploy/backup.sh` no
longer archives covers then; keep the bucket safe with the provider's versioning or replication.

## Sign in with Google or Apple (optional)

**Google.** In Google Cloud Console → APIs & Services → Credentials, create an *OAuth client ID*
of type *Web application* with the authorised redirect URI
`https://<your domain>/api/v1/auth/oauth/google/callback` (the consent screen needs the app name and
a support email). Put the client ID and secret into `.env` as `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET`.

**Apple** (needs a paid Apple Developer account). Create a *Services ID* (this is
`APPLE_CLIENT_ID`), enable *Sign in with Apple* for it with your domain and the return URL
`https://<your domain>/api/v1/auth/oauth/apple/callback`, then create a key with *Sign in with
Apple* and download the `.p8` file. Set `APPLE_TEAM_ID`, `APPLE_KEY_ID` and `APPLE_PRIVATE_KEY`
(the file's contents; in `.env` write the line breaks as `\n`).

Apply with `docker compose -f docker-compose.prod.yml up -d`. The buttons appear on the sign-in and
sign-up pages only for providers that are set up. People who already have an account are matched
by their confirmed email address; two-step sign-in still asks for the code.

## Monitoring and alerts

Three checks tell you about problems before readers do. All are optional and use free services.

**The site is up.** Add an HTTP check in an uptime service (UptimeRobot, Better Stack,
healthchecks.io, ...) for

```
https://library.example.com/api/v1/health
```

It answers `{"status":"ok","database":"ok"}` with status 200 only when the backend can reach
PostgreSQL; alert on anything else.

**Emails are going out.** Create a check that expects a ping every 5 minutes (grace period
10 minutes) in a "dead man's switch" service such as healthchecks.io, put its URL into
`NOTIFIER_PING_URL` in `.env` and run `docker compose -f docker-compose.prod.yml up -d`. The
notifier pings after every cycle, so you are alerted when it stops.

**Backups run.** Create a daily check (grace period a few hours) and put its URL into
`BACKUP_PING_URL` in `.env`. `deploy/backup.sh` pings it after each successful backup and
calls `<url>/fail` when a backup fails, so you hear both about failures and about backups that
stopped running (cron removed, VM down).

Unhandled errors in the backend are reported to Sentry when `SENTRY_DSN` is set (see "Everyday
commands" below).

## 9. Updating

```bash
cd ~/librarium && deploy/backup.sh && git pull
```

Rebuild with fresh base images and pull the newest PostgreSQL 16 image, so security fixes arrive too:

```bash
docker compose -f docker-compose.prod.yml build --pull
```

```bash
docker compose -f docker-compose.prod.yml pull --ignore-buildable
```

```bash
docker compose -f docker-compose.prod.yml up -d
```

```bash
docker image prune -f
```

The `migrate` service applies new Alembic migrations before the backend restarts. Expect a few
seconds of downtime while the single backend container is replaced.

## Automatic deployment (staging, then production)

`.github/workflows/deploy.yml` deploys every commit on `main` that passed CI: first to a staging
server, then a smoke test (`deploy/smoke.sh`: backend and database up, the app and catalogue answer,
the manifest and security headers are there), then — after someone approves it in GitHub — to
production, with a backup first. It can also be started by hand (*Actions → Deploy → Run workflow*,
optionally with a commit id).

1. **A staging server.** Repeat sections 1–8 on a second (small) VM with its own hostname, e.g.
   `staging.library.example.com`, and its own `.env` and secrets. Do not copy production data to it.
2. **A deploy key per server.** On your computer: `ssh-keygen -t ed25519 -f deploy-staging -N ''`.
   On the server, restrict that key to the update script by adding one line to
   `~/.ssh/authorized_keys` (the second server gets its own key, without `DEPLOY_NO_BACKUP=1`):

   ```text
   command="DEPLOY_NO_BACKUP=1 /home/ubuntu/librarium/deploy/update.sh",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA… deploy-staging
   ```

   The script only accepts a commit id, refuses to run over local changes, fetches, checks out
   that commit, rebuilds with fresh base images, pulls PostgreSQL, runs `docker compose … up -d --wait`
   and prunes old images.
3. **GitHub environments.** In the repository's *Settings → Environments* create `staging` and
   `production`; give `production` *Required reviewers*. In each, add the variables `SITE_URL`
   (`https://…`), `DEPLOY_HOST`, `DEPLOY_USER` (e.g. `ubuntu`), `DEPLOY_DIR`
   (`/home/ubuntu/librarium`) and the secrets `DEPLOY_SSH_KEY` (the private key file's contents)
   and `DEPLOY_KNOWN_HOSTS` (the output of `ssh-keyscan <host>`, so an impostor server is refused).

Until the environments have these values the workflow runs but skips the SSH and smoke steps. The
smoke test can be run by hand against any site: `deploy/smoke.sh https://library.example.com`.

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

Container logs are rotated (5 × 10 MB per container), so they do not fill the disk. Backend logs
are JSON lines; every line of one request carries the same `request_id`, which users also see as the
"code" in an unexpected-error message. To find everything about one report:

```bash
docker compose -f docker-compose.prod.yml logs backend | grep '"request_id": "<code>"'
```

**Rotating the two-step sign-in key.** Servers set up before `MFA_ENCRYPTION_KEYS` existed use a
key derived from `JWT_SECRET_KEY` (the backend logs a warning); the same steps move them to their
own key. Put a new key in front of the old ones in `.env` (`MFA_ENCRYPTION_KEYS=new,old`; leave
`old` out the first time), restart, re-encrypt, then remove the old key and restart again:

```bash
docker compose -f docker-compose.prod.yml up -d backend notifier
```

```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.cli rotate-mfa-keys
```

Secrets no key can open (the command counts them) need a reset by an administrator.

**Error reporting (optional).** Put a Sentry (or GlitchTip) DSN into `SENTRY_DSN` in `.env` and run
`docker compose -f docker-compose.prod.yml up -d`; unhandled errors are then reported with their stack
trace, without IP addresses, cookies or request bodies.

## Security notes

- Only ports 22, 80 and 443 are open; PostgreSQL and the backend are reachable only inside Docker.
- `ENVIRONMENT=production` is enforced: the backend refuses to start with a weak `JWT_SECRET_KEY`,
  and cookies are `Secure` and `HttpOnly`.
- Caddy sets HSTS, a Content-Security-Policy (scripts, styles and API calls only from your domain;
  images from any HTTPS host, for book covers), `Permissions-Policy` (the camera only for the site itself, for
  scanning ISBN barcodes; no microphone, location or payments) and the usual hardening headers,
  and ignores client-supplied `X-Forwarded-For`, so the IP addresses stored with sessions cannot be
  spoofed. If you add a third-party script or font later, extend the policy in `deploy/web/Caddyfile`.
- The backend makes outbound HTTPS requests with book data only: Open Library (ISBN lookup),
  Wikidata and Wikipedia (translations) and, when `ANTHROPIC_API_KEY` is set, the Anthropic API.
  Keep `.env` at `chmod 600`; it holds that key along with the other secrets.
- Keep the OS patched (`sudo apt-get update && sudo apt-get upgrade`; Ubuntu installs security
  updates automatically via unattended-upgrades) and use SSH keys only.
- Login, registration, token refresh and password resets are rate-limited per IP address and per email
  (see the main README).

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| `required variable ... is missing a value` | `.env` is missing or incomplete next to `docker-compose.prod.yml`. |
| Site unreachable, or no certificate | DNS not pointing to the VM yet, or port 80/443 closed in the security list or iptables (step 2). Check `logs web`. |
| `502 Bad Gateway` | Backend not running; check `logs backend`. In production it refuses to start with an invalid configuration and prints why. |
| Logged out after every reload | The site was opened by IP or another hostname instead of `DOMAIN`. |
| *Out of capacity* when creating the VM | Retry later or choose another availability domain. |
| VM stopped or reclaimed by Oracle | Oracle may reclaim idle Always Free instances; check their current policy and keep off-VM backups. |
