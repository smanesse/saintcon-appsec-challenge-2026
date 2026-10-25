package com.saintcon.ipm;

import org.springframework.stereotype.Service;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

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

    public List<Entry> extract(byte[] archive) throws IOException {
        Path dest = Files.createTempDirectory("ipm_zip_");
        List<Entry> entries = new ArrayList<>();

        try (ZipInputStream zin = new ZipInputStream(new ByteArrayInputStream(archive))) {
            ZipEntry ze;
            while ((ze = zin.getNextEntry()) != null) {
                if (ze.isDirectory()) {
                    continue;
                }
                byte[] data = IoUtils.readAll(zin);

                File outFile = new File(dest.toFile(), ze.getName());
                File parent = outFile.getParentFile();
                if (parent != null) {
                    parent.mkdirs();
                }
                try {
                    Files.write(outFile.toPath(), data);
                } catch (IOException ignore) {
                }

                entries.add(new Entry(ze.getName(), data));
                zin.closeEntry();
            }
        }
        return entries;
    }
}
