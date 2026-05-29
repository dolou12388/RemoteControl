# Security

RemoteControl is designed for self-hosted personal or small-team use. It relays mouse and keyboard commands to a logged-in Windows desktop client, so deploy it with the same care as any remote-control tool.

## Recommended Deployment

- Use HTTPS/WSS in production.
- Use a long random password for every account.
- Keep public registration disabled unless you intentionally need it.
- Prefer invite-code registration or phone-generated pairing codes for onboarding desktops.
- Keep the built-in login rate limit enabled.
- Keep `.env` and `server/data/` private.
- Run the server on a VPS you control.
- Keep Linux packages and Python dependencies updated.
- Put the service behind Nginx or another reverse proxy.
- Expose only the ports you need.

## Sensitive Files

Do not commit:

```text
server/.env
server/data/
*.log
```

The `.gitignore` file already excludes these paths.

## Threat Model

Anyone who knows a valid username and password can control desktops logged in with that account. Protect credentials carefully.

The project does not currently include:

- multi-factor authentication
- per-device approval
- audit logs

The server includes registration controls, invite-code registration, one-time desktop pairing codes, basic login rate limiting, session expiry, message validation, device timeout checks, and a `/health` endpoint. The Windows desktop client can store saved credentials with current-user DPAPI encryption. These are baseline protections, not a substitute for HTTPS, strong passwords, and careful server access control.

For public or multi-user deployments, consider adding these protections before relying on it for sensitive machines.

## Reporting Issues

Please open a GitHub issue for security concerns that do not expose active credentials or private server details.
