vcl 4.1;

# A.L.I.E.N. Docking Bay — EDGE cache (Varnish). The only exposed service.
# Terminates client HTTP, serves the console, and reverse-proxies the launch
# API to the origin on container-loopback.

backend origin {
    .host = "127.0.0.1";
    .port = "9090";
}

sub vcl_recv {
    # Single-origin edge: the cache key doesn't depend on which hostname the
    # client used to reach us.
    set req.http.host = "docking-bay";

    # Cache static assets; everything else is treated as per-user and passed
    # straight through to the origin.
    if (req.method != "GET" && req.method != "HEAD") {
        return (pass);
    }
    if (regsub(req.url, "\?.*$", "") ~ "(?i)\.(css|js|png|jpe?g|gif|svg|ico|woff2?)$") {
        return (hash);
    }
    return (pass);
}

sub vcl_backend_response {
    if (regsub(bereq.url, "\?.*$", "") ~ "(?i)\.(css|js|png|jpe?g|gif|svg|ico|woff2?)$") {
        # Never cache errors or responses the origin marked non-shareable.
        if (beresp.status != 200
            || beresp.http.Cache-Control ~ "(?i)(private|no-store|no-cache)") {
            set beresp.uncacheable = true;
            set beresp.ttl = 120s;
            return (deliver);
        }
        unset beresp.http.Set-Cookie;
        set beresp.ttl = 20s;
        set beresp.grace = 0s;
    }
}

sub vcl_deliver {
    if (obj.hits > 0) {
        set resp.http.X-Cache = "HIT";
    } else {
        set resp.http.X-Cache = "MISS";
    }
}
