package com.saintcon.ipm;

import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.URL;

/**
 * Fetches a source image from a user-supplied URL for /convert-url.
 *
 * Only http(s) is fetched, redirects are not followed, and the destination
 * host must not resolve to a loopback, link-local (cloud metadata),
 * any-local or multicast address. Responses are capped in size.
 */
@Service
public class UrlFetchService {

    public static class Fetched {
        public final byte[] data;
        public final String name;

        public Fetched(byte[] data, String name) {
            this.data = data;
            this.name = name;
        }
    }

    private static final int MAX_BYTES = 64 * 1024 * 1024;

    public Fetched fetch(String url) throws IOException {
        // (This was a pruned, unscored SSRF: any scheme, including file://,
        // any host, redirects followed.)
        URL target = new URL(url);
        String scheme = target.getProtocol().toLowerCase(java.util.Locale.ROOT);
        if (!scheme.equals("http") && !scheme.equals("https")) {
            throw new IOException("only http and https URLs are supported");
        }
        for (InetAddress addr : InetAddress.getAllByName(target.getHost())) {
            if (addr.isLoopbackAddress() || addr.isLinkLocalAddress() || addr.isAnyLocalAddress()
                    || addr.isMulticastAddress()) {
                throw new IOException("destination not allowed");
            }
        }
        HttpURLConnection conn = (HttpURLConnection) target.openConnection();
        conn.setConnectTimeout(5000);
        conn.setReadTimeout(5000);
        conn.setInstanceFollowRedirects(false);
        if (conn.getResponseCode() / 100 != 2) {
            conn.disconnect();
            throw new IOException("fetch failed: HTTP " + conn.getResponseCode());
        }

        try (InputStream in = conn.getInputStream()) {
            byte[] data = in.readNBytes(MAX_BYTES + 1);
            if (data.length > MAX_BYTES) {
                throw new IOException("fetched resource too large");
            }
            return new Fetched(data, deriveName(target));
        }
    }

    private String deriveName(URL target) {
        String path = target.getPath();
        int slash = path.lastIndexOf('/');
        String name = (slash >= 0) ? path.substring(slash + 1) : path;
        if (name.isBlank()) {
            name = "fetched";
        }
        return name;
    }
}
