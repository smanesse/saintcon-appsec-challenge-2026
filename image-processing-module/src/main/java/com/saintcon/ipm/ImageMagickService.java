package com.saintcon.ipm;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.TimeUnit;

@Service
public class ImageMagickService {

    @Value("${ipm.magick}")
    private String magick;

    @Value("${ipm.stdsize}")
    private int stdsize;

    /**
     * Convert {@code data} to PNG bytes.
     *
     * @param inputName client-supplied source name (multipart filename, or a
     *                  name derived from a URL/zip entry). Informational only:
     *                  never used as a path or ImageMagick argument.
     * @param data      the uploaded/fetched source bytes.
     * @param width     raw width string (defaults to stdsize).
     * @param height    raw height string (defaults to stdsize).
     * @param format    raw output coder (defaults to "png").
     * @param outName   client-chosen stored name; not used for any local path.
     */
    public byte[] convert(String inputName, byte[] data,
                          String width, String height,
                          String format, String outName) throws IOException, InterruptedException {

        Path work = Files.createTempDirectory("ipm_");

        // The client-supplied name is never used as an ImageMagick argument or
        // a path: the bytes are written to a fixed file in the private work dir
        // and read back with an explicit coder chosen from the content's magic
        // bytes (an allow-list of raster formats plus SVG). The output goes to
        // a fixed file with an allow-listed coder, and a restrictive
        // policy.xml (see policyDir) disables ImageMagick's file-reading /
        // scripting coders and indirect "@file" reads. (#2 was passing the
        // client-supplied name straight through as the magick source, so coder
        // syntax in it read arbitrary host files into the output.)
        String inCoder = sniffInputCoder(data);
        if (inCoder == null) {
            throw new IOException("unsupported or unrecognised image type");
        }
        if (inCoder.equals("png")) {
            // CVE-2022-44268 (pinned ImageMagick 7.1.0-48): a PNG text chunk
            // keyed "profile" makes magick read a named host file and embed
            // it in the output. The image is pinned in the Dockerfile, so text
            // chunks are dropped here before magick sees the file, and -strip
            // (below) removes any profile from the output regardless.
            data = stripPngTextChunks(data);
        }
        Path in = work.resolve("input");
        Files.write(in, data);

        String w = (width == null || width.isBlank()) ? String.valueOf(stdsize) : width;
        String h = (height == null || height.isBlank()) ? String.valueOf(stdsize) : height;
        if (!validDimension(w) || !validDimension(h)) {
            throw new IOException("width/height must be integers between 1 and " + MAX_DIMENSION);
        }
        String coder = (format == null || format.isBlank()) ? "png" : format.toLowerCase(Locale.ROOT);
        if (!OUTPUT_CODERS.contains(coder)) {
            throw new IOException("unsupported output format: " + coder);
        }
        Path outFile = work.resolve("output");

        String resize = w + "x" + h;

        // ImageMagick is exec'd directly with an argument vector - no shell is
        // involved, so metacharacters in any client-supplied value are inert
        // characters inside a single argument. (#1 was building this command
        // line by string concatenation and running it with `sh -c`.)
        //
        // Resource limits come first so they govern decoding: a small input
        // that declares a huge canvas is refused instead of being rasterised.
        // SVGs are additionally size-checked before this point (see
        // SvgMetadataService). (#3 was running magick with no limits at all.)
        List<String> cmd = new ArrayList<>();
        cmd.add(magick);
        for (String[] lim : LIMITS) {
            cmd.add("-limit");
            cmd.add(lim[0]);
            cmd.add(lim[1]);
        }
        cmd.add(inCoder + ":" + in.toAbsolutePath());
        cmd.add("-resize");
        cmd.add(resize);
        cmd.add("-strip");
        cmd.add(coder + ":" + outFile.toAbsolutePath());

        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.environment().put("MAGICK_CONFIGURE_PATH", policyDir().toString());
        pb.directory(work.toFile());
        pb.redirectErrorStream(true);
        Process proc = pb.start();

        String output = new String(IoUtils.readAll(proc.getInputStream()));
        boolean finished = proc.waitFor(60, TimeUnit.SECONDS);
        if (!finished) {
            proc.destroyForcibly();
            throw new IOException("ImageMagick timed out");
        }

        if (!Files.exists(outFile)) {
            throw new IOException("ImageMagick produced no output (exit="
                    + proc.exitValue() + "): " + output);
        }
        return Files.readAllBytes(outFile);
    }

    private static final int MAX_DIMENSION = 8192;

    /** Per-run ImageMagick resource limits (also mirrored in POLICY_XML). */
    private static final String[][] LIMITS = {
            {"width", "8192"}, {"height", "8192"}, {"area", "64MP"},
            {"memory", "256MiB"}, {"map", "512MiB"}, {"disk", "1GiB"}, {"time", "30"},
    };

    /** Output coders a client may request. */
    private static final Set<String> OUTPUT_CODERS =
            Set.of("png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff");

    private static boolean validDimension(String v) {
        if (!v.matches("[0-9]{1,5}")) {
            return false;
        }
        int n = Integer.parseInt(v);
        return n >= 1 && n <= MAX_DIMENSION;
    }

    /**
     * Identify the input format from its leading bytes. Only these formats are
     * ever handed to ImageMagick, each with an explicit coder prefix, so the
     * input can never select a different (file-reading or scripting) coder.
     */
    static String sniffInputCoder(byte[] d) {
        if (startsWith(d, 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A)) return "png";
        if (startsWith(d, 0xFF, 0xD8, 0xFF)) return "jpeg";
        if (startsWith(d, 'G', 'I', 'F', '8')) return "gif";
        if (startsWith(d, 'B', 'M')) return "bmp";
        if (startsWith(d, 'I', 'I', 0x2A, 0x00) || startsWith(d, 'M', 'M', 0x00, 0x2A)) return "tiff";
        if (d.length >= 12 && startsWith(d, 'R', 'I', 'F', 'F')
                && d[8] == 'W' && d[9] == 'E' && d[10] == 'B' && d[11] == 'P') return "webp";
        String head = new String(d, 0, Math.min(d.length, 512), StandardCharsets.ISO_8859_1)
                .trim().toLowerCase(Locale.ROOT);
        if (head.startsWith("<?xml") || head.startsWith("<svg")) {
            return head.contains("<svg") ? "svg" : null;
        }
        return null;
    }

    /**
     * Return the PNG with its tEXt/zTXt/iTXt chunks removed. Chunk framing is
     * validated as we go; a malformed PNG is returned unchanged for magick to
     * reject.
     */
    static byte[] stripPngTextChunks(byte[] png) {
        ByteArrayOutputStream out = new ByteArrayOutputStream(png.length);
        out.write(png, 0, 8);
        int pos = 8;
        while (pos + 12 <= png.length) {
            long len = ((png[pos] & 0xFFL) << 24) | ((png[pos + 1] & 0xFF) << 16)
                    | ((png[pos + 2] & 0xFF) << 8) | (png[pos + 3] & 0xFF);
            if (len > png.length - pos - 12) {
                return png;
            }
            String type = new String(png, pos + 4, 4, StandardCharsets.ISO_8859_1);
            int total = (int) len + 12;
            if (!type.equals("tEXt") && !type.equals("zTXt") && !type.equals("iTXt")) {
                out.write(png, pos, total);
            }
            pos += total;
        }
        if (pos != png.length) {
            return png;
        }
        return out.toByteArray();
    }

    private static boolean startsWith(byte[] d, int... prefix) {
        if (d.length < prefix.length) return false;
        for (int i = 0; i < prefix.length; i++) {
            if ((d[i] & 0xFF) != prefix[i]) return false;
        }
        return true;
    }

    /**
     * ImageMagick security policy, written once to a private directory and
     * picked up via MAGICK_CONFIGURE_PATH for every magick run. Disables the
     * coders that read files or run scripts and indirect "@file" reads.
     */
    private static final String POLICY_XML = """
            <?xml version="1.0" encoding="UTF-8"?>
            <policymap>
              <policy domain="coder" rights="none" pattern="{LABEL,CAPTION,TEXT,MSL,MVG,URL,HTTP,HTTPS,FTP,EPHEMERAL,SHOW,WIN,PLT,PS,PS2,PS3,EPS,EPI,EPSF,EPSI,PDF,XPS}" />
              <policy domain="path" rights="none" pattern="@*" />
              <policy domain="resource" name="width" value="8192" />
              <policy domain="resource" name="height" value="8192" />
              <policy domain="resource" name="area" value="64MP" />
              <policy domain="resource" name="memory" value="256MiB" />
              <policy domain="resource" name="map" value="512MiB" />
              <policy domain="resource" name="disk" value="1GiB" />
              <policy domain="resource" name="time" value="30" />
            </policymap>
            """;

    private static Path policyDir;

    private static synchronized Path policyDir() throws IOException {
        if (policyDir == null) {
            Path dir = Files.createTempDirectory("ipm_magick_policy_");
            Files.writeString(dir.resolve("policy.xml"), POLICY_XML);
            policyDir = dir;
        }
        return policyDir;
    }
}
