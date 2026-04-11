# OSINT intelligence sources and techniques

# OSINT Threat Intel Sources for the project

## Tier 1 — Vendor Security Advisory Pages (most authoritative)

### Core Infrastructure
| Component | Source | URL | Format |
|---|---|---|---|
| Kubernetes/k3s | Official CVE Feed | https://kubernetes.io/docs/reference/issues-security/official-cve-feed/ | JSON+RSS |
| k3s | CVE Portal (scans) | https://github.com/k3s-io/scans | GitHub |
| Rancher/k3s | Security Advisories | https://ranchermanager.docs.rancher.com/reference-guides/rancher-security/security-advisories-and-cves | Web |
| HashiCorp Vault | Security forum | https://discuss.hashicorp.com/c/security/52 | Web |
| HashiCorp Vault | Vulnerability mgmt | https://www.hashicorp.com/en/trust/security/vulnerability-management | Web |
| Traefik | GitHub Security Advisories | https://github.com/traefik/traefik/security/advisories | GitHub |
| Authentik | GitHub Security Advisories | https://github.com/goauthentik/authentik/security/advisories | GitHub |
| Authentik | CVE docs | https://docs.goauthentik.io/security/cves/ | Web |
| Flux CD | GitHub advisories | https://github.com/fluxcd/flux2/security/advisories | GitHub |
| Kyverno | GitHub advisories | https://github.com/kyverno/kyverno/security/advisories | GitHub |
| cert-manager | GitHub advisories | https://github.com/cert-manager/cert-manager/security/advisories | GitHub |
| Headscale | GitHub releases | https://github.com/juanfont/headscale/releases | GitHub |
| Pi-hole | GitHub releases | https://github.com/pi-hole/pi-hole/releases | GitHub |
| Ubuntu 24.04 | USN (Security Notices) | https://ubuntu.com/security/notices | RSS |
| Linux kernel | Security advisories | https://lore.kernel.org/linux-cve-announce/ | Mailing list |

### Security / SOC Stack
| Component | Source | URL | Format |
|---|---|---|---|
| Elastic (ES/Kibana/Logstash/Agent) | Security Announcements Forum | https://discuss.elastic.co/c/announcements/security-announcements/31 | RSS |
| Elastic | Security Issues page | https://www.elastic.co/community/security | Web |
| Wazuh | GitHub releases + security | https://github.com/wazuh/wazuh/releases | GitHub |
| Velociraptor | GitHub releases | https://github.com/Velocidex/velociraptor/releases | GitHub |
| Greenbone/OpenVAS | Community advisories | https://forum.greenbone.net/c/vulnerability-tests/ | Web |
| MISP | GitHub releases | https://github.com/MISP/MISP/releases | GitHub |
| OpenCTI | GitHub releases | https://github.com/OpenCTI-Platform/opencti/releases | GitHub |
| Cortex | GitHub releases | https://github.com/TheHive-Project/Cortex/releases | GitHub |
| n8n | Security advisories | https://community.n8n.io/c/security-advisories/ | Web |
| n8n | Blog security posts | https://blog.n8n.io/ (filter: security) | Web |
| Snort | Security advisories | https://www.snort.org/advisories | Web |

### Platform Services
| Component | Source | URL | Format |
|---|---|---|---|
| GitLab CE | Security releases blog | https://about.gitlab.com/releases/categories/releases/ | RSS |
| GitLab CE | Security page | https://gitlab.com/gitlab-org/gitlab/-/security | Web |
| PostgreSQL | Security info | https://www.postgresql.org/support/security/ | Web |
| Redis | GitHub advisories | https://github.com/redis/redis/security/advisories | GitHub |
| Nginx | Security advisories | https://nginx.org/en/security_advisories.html | Web |
| Docker | Security advisories | https://docs.docker.com/security/ | Web |
| MinIO | GitHub advisories | https://github.com/minio/minio/security/advisories | GitHub |
| RabbitMQ | GitHub advisories | https://github.com/rabbitmq/rabbitmq-server/security/advisories | GitHub |
| Ollama | GitHub advisories | https://github.com/ollama/ollama/security/advisories | GitHub |
| Litestream | GitHub releases | https://github.com/benbjohnson/litestream/releases | GitHub |

## Tier 2 — Aggregator CVE Feeds (cross-cutting)
| Source | URL | Covers | Format |
|---|---|---|---|
| NVD API 2.0 | https://nvd.nist.gov/developers/vulnerabilities | All CVEs, CVSS, CPE | REST API |
| CISA KEV Catalog | https://www.cisa.gov/known-exploited-vulnerabilities-catalog | Actively exploited — highest signal | JSON+CSV |
| stack.watch | https://stack.watch/ | Custom RSS per product | RSS |
| cvedetails.com | https://www.cvedetails.com/ | Per-vendor/product CVE lists | Web |
| GitHub Advisory Database | https://github.com/advisories | All GitHub-tracked advisories | API+RSS |
| OSV.dev | https://osv.dev/ | Open source vuln database | API |

## Tier 3 — Threat Intel and News
| Source | URL | Focus |
|---|---|---|
| CISA Alerts | https://www.cisa.gov/news-events/cybersecurity-advisories | US-CERT alerts |
| Abuse.ch | https://abuse.ch/ | Malware/botnet — feeds MISP |
| AlienVault OTX | https://otx.alienvault.com/ | Crowd-sourced threat intel |
| GreyNoise Trends | https://viz.greynoise.io/trends | Active CVE exploitation |
| Bert-JanP/Open-Source-Threat-Intel-Feeds | https://github.com/Bert-JanP/Open-Source-Threat-Intel-Feeds | Curated free feeds |
| awesome-threat-intelligence | https://github.com/hslatman/awesome-threat-intelligence | Master TI resource list |

## Notable Recent CVEs (as of 2026-03-26)
- n8n: CVE-2026-21858 (CVSS 10, unauth RCE), CVE-2026-25049 (CVSS 9.9) — CRITICAL
- Authentik: CVE-2026-25227 (RCE via property mapping) — fixed 2025.12.4+
- Traefik: CVE-2026-32595 (BasicAuth timing), CVE-2026-29777 (k8s gateway injection), CVE-2026-32305 (mTLS bypass)
- HashiCorp Vault: CVE-2025-6000 (code exec by privileged operator)

---

# OSINT Monitoring Checklist — Weekly Security Sweep

Check in this order (highest signal first):

1. **CISA KEV** — https://www.cisa.gov/known-exploited-vulnerabilities-catalog
   New additions = actively exploited = patch immediately

2. **Elastic Security Announcements** — https://discuss.elastic.co/c/announcements/security-announcements/31
   ES 8.17.3 / Kibana / Logstash / Agent

3. **GitLab security releases** — https://about.gitlab.com/releases/categories/releases/
   GitLab CE 18.2.8

4. **Traefik GitHub advisories** — https://github.com/traefik/traefik/security/advisories
   Recent critical: path traversal WASM plugin, HTTP smuggling

5. **Authentik GitHub advisories** — https://github.com/goauthentik/authentik/security/advisories
   Recent: CVE-2026-25227 RCE via property mapping

6. **HashiCorp Vault security** — https://discuss.hashicorp.com/c/security/52
   Recent: CVE-2025-6000 arbitrary code exec

7. **Kubernetes CVE Feed** — https://kubernetes.io/docs/reference/issues-security/official-cve-feed/
   k3s + core k8s

8. **n8n security advisories** — https://community.n8n.io/c/security-advisories/
   HIGH PRIORITY: CVE-2026-21858 (CVSS 10 unauth RCE), CVE-2026-25049 (CVSS 9.9)

9. **Wazuh/MISP/OpenCTI GitHub releases** — check for security-tagged releases
   - https://github.com/wazuh/wazuh/releases
   - https://github.com/MISP/MISP/releases
   - https://github.com/OpenCTI-Platform/opencti/releases

10. **Ubuntu USN** — https://ubuntu.com/security/notices
    Filter for packages on k3s nodes + nas-node + ai-node

11. **stack.watch custom feed** — https://stack.watch/
    Configure for all the project components for single RSS

## Automation quick wins
- CISA KEV has JSON endpoint — poll via n8n
- Elastic forum has RSS — consume via ntfy or n8n
- GitHub advisories have Atom feeds: /security/advisories.atom
- stack.watch generates custom RSS per product watch list
