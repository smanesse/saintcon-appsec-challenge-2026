package com.saintcon.ipm;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

final class IoUtils {
    private IoUtils() {
    }

    static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] chunk = new byte[8192];
        int n;
        while ((n = in.read(chunk)) != -1) {
            buf.write(chunk, 0, n);
        }
        return buf.toByteArray();
    }
}
