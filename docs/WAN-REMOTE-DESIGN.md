# MAYA AI — WAN Remote Control Design

> Status: design + skeleton; milestones 1–2 complete (19 Nov 2026). Relay/TLS not deployed.
> Code: `JARVIS/custom/server/wan_relay.py`, `JARVIS/custom/server/tls.py`
> Contract: `docs/API-CONTRACT.md` §18.

## Problem

LAN-only remote control works on Wi-Fi/hotspot. Internet (WAN) access needs:

- NAT traversal (both ends may be behind routers).
- A stable address when the laptop has a dynamic IP.
- TLS so the control stream is not cleartext on the open Internet.
- Auth that is at least as strong as the LAN pairing token.

## Options compared

| Option | Complexity | Cost | Latency | Maintenance | NAT traversal | Verdict |
|---|---|---|---|---|---|---|
| Custom relay (TURN-like) | High | Low (one VPS) | Medium | High | Good | Skeleton provided |
| Tailscale / Headscale | Low | Free tier | Low (DERP fallback) | Low | Excellent | **Recommended** |
| Cloudflare Tunnel | Low | Free | Medium | Low | Excellent | Good, but third-party |
| ngrok | Low | Free/paid | Medium | Low | Good | Third-party, dynamic URLs |

### Recommendation

**Tailscale (or Headscale for self-hosted)** is the best default: it gives a
stable private IP, NAT traversal, and WireGuard-grade encryption with almost
no code. Maya would treat the Tailscale IP as another LAN host. The custom
relay skeleton is kept for the case where the user wants a fully self-hosted
path.

## Threat model

- LAN: HTTP cleartext is acceptable on a trusted private network.
- WAN: TLS is mandatory. The relay must never see plaintext control traffic
  (end-to-end TLS between phone and laptop, relay only tunnels).
- Pairing token stays the same; WAN does not weaken auth.

## Proposed architecture (Tailscale path)

```
Phone app ──TLS/WireGuard──> Tailscale network ──> Laptop (Tailscale IP)
```

1. Install Tailscale on laptop + phone; log in with the same tailnet.
2. Laptop advertises its Tailscale IP in `/health` as `wan_host`.
3. Phone pairs over LAN once, then can switch to the Tailscale IP.
4. All existing endpoints (`/pc/screen`, `/pc/input`, `/pc/files/*`) work
   unchanged over the Tailscale IP.

## Proposed architecture (custom relay path)

```
Phone ──TLS──> Relay (VPS) <──TLS── Laptop
```

- Relay only forwards framed bytes; it cannot decrypt end-to-end payloads.
- Laptop registers with `token`; phone connects with the same token.
- 4-byte length framing + magic (`wan_relay.py`).
- Self-signed CA for LAN testing; ACME for real WAN certs.

## Capability negotiation

- `/health` gains `wan_host` (Tailscale IP) and `capabilities` includes `wan`.
- Phone shows "Internet mode available" when `wan` is present.

## Config

```yaml
server:
  wan:
    enabled: false
    relay_url: ""          # custom relay host:port
    cert_path: ""          # self-signed or ACME cert
    key_path: ""
    mode: lan              # lan | wan
```

## Milestones

1. ✅ Add `wan_host` to `/health` + capabilities (code only). The advertised
   host comes from `server.wan.host`, falling back to `relay_url`.
2. ✅ Tailscale install guide in `WINDOWS APPLICATION/windows/README.md` → "Internet (WAN)
   remote — Tailscale".
3. Optional: custom relay deployment script (VPS) — deferred (user action).
4. Optional: ACME/Let's Encrypt cert renewal — deferred (user action).

Config keys `host`, `relay_url`, `cert_path`, `key_path` and `mode` are now
parsed into `ServerSettings`. The framed relay client buffers partial/multiple
frames correctly; the relay server and WAN TLS remain skeletons by design.

## Honest limits

- No relay server is deployed; WAN is not usable today.
- Tailscale path needs the user to install/log in (user action).
- The custom relay is a skeleton; production hardening (rate limits, DDoS,
  cert rotation) is not done.
