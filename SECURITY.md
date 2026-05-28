# Security

RemoteControl is designed for self-hosted personal or small-team use. It relays mouse and keyboard commands to a logged-in Windows desktop client, so deploy it with the same care as any remote-control tool.

## Recommended Deployment

- Use HTTPS/WSS in production.
- Use a long random password for every account.
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
- brute-force lockout
- per-device approval
- audit logs
- encrypted local storage for desktop credentials

For public or multi-user deployments, consider adding these protections before relying on it for sensitive machines.

## Reporting Issues

Please open a GitHub issue for security concerns that do not expose active credentials or private server details.
