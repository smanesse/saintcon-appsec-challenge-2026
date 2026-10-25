package com.saintcon.ipm;

import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLConnection;

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

    public Fetched fetch(String url) throws IOException {
        URL target = new URL(url);
        URLConnection conn = target.openConnection();
        conn.setConnectTimeout(5000);
        conn.setReadTimeout(5000);
        if (conn instanceof HttpURLConnection httpConn) {
            httpConn.setInstanceFollowRedirects(true);
        }

        try (InputStream in = conn.getInputStream()) {
            return new Fetched(IoUtils.readAll(in), deriveName(target));
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
