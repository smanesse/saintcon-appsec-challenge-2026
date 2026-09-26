package com.saintcon.ipm;

import org.springframework.stereotype.Service;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Extracts a .zip archive of images for /convert-batch.
 * Entries are written only inside a private temp directory, and entry
 * count / per-entry size / total size are capped.
 */
@Service
public class ZipService {

    public static class Entry {
        public final String name;
        public final byte[] data;

        public Entry(String name, byte[] data) {
            this.name = name;
            this.data = data;
        }
    }

    private static final int MAX_ENTRIES = 100;
    private static final int MAX_ENTRY_BYTES = 32 * 1024 * 1024;
    private static final long MAX_TOTAL_BYTES = 128L * 1024 * 1024;

    public List<Entry> extract(byte[] archive) throws IOException {
        Path dest = Files.createTempDirectory("ipm_zip_").toAbsolutePath().normalize();
        long total = 0;
        List<Entry> entries = new ArrayList<>();

        try (ZipInputStream zin = new ZipInputStream(new ByteArrayInputStream(archive))) {
            ZipEntry ze;
            while ((ze = zin.getNextEntry()) != null) {
                if (ze.isDirectory()) {
                    continue;
                }
                if (entries.size() >= MAX_ENTRIES) {
                    throw new IOException("archive has too many entries");
                }
                byte[] data = zin.readNBytes(MAX_ENTRY_BYTES + 1);
                if (data.length > MAX_ENTRY_BYTES) {
                    throw new IOException("archive entry too large: " + ze.getName());
                }
                total += data.length;
                if (total > MAX_TOTAL_BYTES) {
                    throw new IOException("archive expands too large");
                }

                // Only write entries whose resolved path stays inside dest;
                // anything else (absolute, "../") is skipped on disk. (This was
                // a pruned zip-slip / disk-exhaustion bug: unchecked paths and
                // no size caps.)
                try {
                    Path outFile = dest.resolve(ze.getName()).normalize();
                    if (outFile.startsWith(dest) && !outFile.equals(dest)) {
                        Files.createDirectories(outFile.getParent());
                        Files.write(outFile, data);
                    }
                } catch (IOException | java.nio.file.InvalidPathException ignore) {
                    // best-effort: still return bytes for conversion below
                }

                entries.add(new Entry(ze.getName(), data));
                zin.closeEntry();
            }
        }
        return entries;
    }
}
