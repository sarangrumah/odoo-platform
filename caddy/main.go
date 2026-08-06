// Custom Caddy build for the eal-hub.erajaya.com front door.
//
// This file exists instead of an `xcaddy build --with ...` one-liner because the
// front door terminates TLS for production and the build has to be able to pin
// TRANSITIVE dependencies, not just plugins. The first version of this image used
// xcaddy and shipped 20 HIGH/CRITICAL CVEs that trivy found immediately: Caddy
// 2.11.3 itself (2 CVEs, fixed in 2.11.4), golang.org/x/crypto (9),
// golang.org/x/net (3), x/text, grpc, go-jose and the Go stdlib. xcaddy resolves
// whatever the pinned Caddy's go.mod asks for and gives no lever to raise a
// transitive module; a plain `go build` over an explicit go.mod does.
//
// Keep the plugin list here in step with caddy/Dockerfile's `go get` lines — an
// import with no matching `go get` still builds (Go resolves the latest), which
// would silently unpin it.
package main

import (
	caddycmd "github.com/caddyserver/caddy/v2/cmd"

	// The standard module set: everything a stock caddy:2-alpine can do. Without
	// it this binary would parse the Caddyfile and then fail to load reverse_proxy,
	// file_server, tls and the rest.
	_ "github.com/caddyserver/caddy/v2/modules/standard"

	// ModSecurity-compatible WAF (SecLang), which is what runs the OWASP Core Rule
	// Set — see caddy/coraza/ for the configuration and the tuning rationale.
	_ "github.com/corazawaf/coraza-caddy/v2"

	// Per-client-IP request ceilings; the Caddyfile uses it for the credential
	// paths and a loose general zone.
	_ "github.com/mholt/caddy-ratelimit"
)

func main() {
	caddycmd.Main()
}
