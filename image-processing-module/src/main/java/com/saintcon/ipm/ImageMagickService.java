package com.saintcon.ipm;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
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

        String cmd = magick + " " + inputName
                + " -resize " + resize + " "
                + coder + ":" + outName;

        ProcessBuilder pb = new ProcessBuilder("sh", "-c", cmd);
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
