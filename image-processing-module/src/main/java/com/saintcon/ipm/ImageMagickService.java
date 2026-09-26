package com.saintcon.ipm;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

@Service
public class ImageMagickService {

    @Value("${ipm.magick}")
    private String magick;

    @Value("${ipm.stdsize}")
    private int stdsize;

    public byte[] convert(String inputName, byte[] data,
                          String width, String height,
                          String format, String outName) throws IOException, InterruptedException {

        Path work = Files.createTempDirectory("ipm_");

        if (inputName == null || inputName.isBlank()) {
            inputName = "upload";
        }
        try {
            Path in = work.resolve(inputName);
            Files.write(in, data);
        } catch (Exception ignore) {
        }

        String w = (width == null || width.isBlank()) ? String.valueOf(stdsize) : width;
        String h = (height == null || height.isBlank()) ? String.valueOf(stdsize) : height;
        String coder = (format == null || format.isBlank()) ? "png" : format;
        if (outName == null || outName.isBlank()) {
            outName = "out.png";
        }

        String resize = w + "x" + h;

        // ImageMagick is exec'd directly with an argument vector - no shell is
        // involved, so metacharacters in any client-supplied value are inert
        // characters inside a single argument. (#1 was building this command
        // line by string concatenation and running it with `sh -c`.)
        //
        // VULN (coder-LFI / arbitrary file read, #2): inputName is passed
        // straight through as the magick source, so ImageMagick coder tricks
        // like `label:@/etc/passwd`, `@/etc/passwd`, MVG/MSL, or a leading `-`
        // are honoured and read host files into the rendered PNG (retrievable
        // via GET /image/{name}). Root cause: no coder allow-list / policy.xml.
        //
        // VULN (decompression-bomb / pixel-flood DoS, #3): no -limit area /
        // memory / disk and no policy.xml, so a tiny input that decodes to a
        // gigapixel canvas exhausts memory/CPU. Root cause: missing resource
        // limits.
        //
        // BUG, not independently scoreable (pruned from vuln_tests): the same
        // missing -limit/policy.xml also lets an uploaded SVG/MVG whose content
        // references a remote resource (<image xlink:href="http://internal/">)
        // make ImageMagick's delegate fetch that URL server-side. Real by code
        // review, but this build's pinned inkscape/rsvg-convert both refuse
        // remote hrefs outright, so it never fires over the network here - see
        // vuln_tests/README.md's "Pruned / reclassified" section.
        List<String> cmd = new ArrayList<>();
        cmd.add(magick);
        cmd.add(inputName);
        cmd.add("-resize");
        cmd.add(resize);
        cmd.add(coder + ":" + outName);

        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.directory(work.toFile());
        pb.redirectErrorStream(true);
        Process proc = pb.start();

        String output = new String(IoUtils.readAll(proc.getInputStream()));
        boolean finished = proc.waitFor(60, TimeUnit.SECONDS);
        if (!finished) {
            proc.destroyForcibly();
            throw new IOException("ImageMagick timed out");
        }

        Path outFile = work.resolve(outName);
        if (!Files.exists(outFile)) {
            throw new IOException("ImageMagick produced no output (exit="
                    + proc.exitValue() + "): " + output);
        }
        return Files.readAllBytes(outFile);
    }
}
