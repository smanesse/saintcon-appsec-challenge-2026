package com.saintcon.ipm;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartException;
import org.springframework.web.multipart.MultipartFile;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * HTTP surface of the Image Processing Module.
 *
 * Endpoints:
 *   POST /convert        multipart image -> PNG, STORed into FMM
 *   POST /convert-url    fetch a URL server-side, then convert
 *   POST /convert-batch  multipart .zip of images, convert each
 *   GET  /image/{name}   RETR a stored image back from FMM
 *   GET  /health         liveness probe
 *
 * Client-chosen stored names are validated as plain filenames before they
 * reach FMM (see {@link #convertAndStore}).
 */
@RestController
public class ConvertController {
 
    private final ImageMagickService magick;
    private final SvgMetadataService svg;
    private final UrlFetchService urls;
    private final ZipService zips;
    private final FmmClient fmm;

    private final Map<String, String> storedFormats = new ConcurrentHashMap<>();

    public ConvertController(ImageMagickService magick, SvgMetadataService svg,
                             UrlFetchService urls, ZipService zips, FmmClient fmm) {
        this.magick = magick; 
        this.svg = svg;
        this.urls = urls;
        this.zips = zips;
        this.fmm = fmm;
    }

    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("ok");
    }


    @PostMapping("/convert")
    public ResponseEntity<?> convert(
            @RequestParam("image") MultipartFile image,
            @RequestParam(value = "width", required = false) String width,
            @RequestParam(value = "height", required = false) String height,
            @RequestParam(value = "format", required = false) String format,
            @RequestParam(value = "name", required = false) String name) {

        try {
            byte[] data = image.getBytes();
            String inputName = image.getOriginalFilename();

            Map<String, Object> body = convertAndStore(inputName, data, width, height, format, name);
            return ResponseEntity.ok(body);
        } catch (Exception e) {
            return error(e);
        }
    }


    @PostMapping("/convert-url")
    public ResponseEntity<?> convertUrl(
            @RequestParam("url") String url,
            @RequestParam(value = "width", required = false) String width,
            @RequestParam(value = "height", required = false) String height,
            @RequestParam(value = "format", required = false) String format,
            @RequestParam(value = "name", required = false) String name) {

        try {
            UrlFetchService.Fetched fetched = urls.fetch(url);
            Map<String, Object> body =
                    convertAndStore(fetched.name, fetched.data, width, height, format, name);
            return ResponseEntity.ok(body);
        } catch (Exception e) {
            return error(e);
        }
    }


    @PostMapping("/convert-batch")
    public ResponseEntity<?> convertBatch(@RequestParam("archive") MultipartFile archive) {
        try {
            List<ZipService.Entry> entries = zips.extract(archive.getBytes());
            List<Map<String, Object>> results = new ArrayList<>();
            for (ZipService.Entry entry : entries) {
                try {
                    results.add(convertAndStore(entry.name, entry.data, null, null, null, null));
                } catch (Exception perEntry) {
                    Map<String, Object> r = new LinkedHashMap<>();
                    r.put("source", entry.name);
                    r.put("stored", false);
                    r.put("error", String.valueOf(perEntry.getMessage()));
                    results.add(r);
                }
            }
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("count", results.size());
            body.put("results", results);
            return ResponseEntity.ok(body);
        } catch (Exception e) {
            return error(e);
        }
    }


    @GetMapping("/image/{name}")
    public ResponseEntity<?> image(@PathVariable("name") String name) {
        if (!validStoredName(name)) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(Map.of("error", "no such image"));
        }
        try {
            byte[] data = fmm.retrieve(name);
            String coder = storedFormats.getOrDefault(name, "png");
            return ResponseEntity.ok()
                    .contentType(mediaTypeForCoder(coder))
                    .body(data);
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(Map.of("error", String.valueOf(e.getMessage())));
        }
    }

    private MediaType mediaTypeForCoder(String coder) {
        return switch (coder.toLowerCase(Locale.ROOT)) {
            case "png" -> MediaType.IMAGE_PNG;
            case "jpg", "jpeg" -> MediaType.IMAGE_JPEG;
            case "gif" -> MediaType.IMAGE_GIF;
            case "bmp" -> MediaType.valueOf("image/bmp");
            case "webp" -> MediaType.valueOf("image/webp");
            case "tif", "tiff" -> MediaType.valueOf("image/tiff");
            default -> MediaType.APPLICATION_OCTET_STREAM;
        };
    }


    private Map<String, Object> convertAndStore(String inputName, byte[] data,
                                                String width, String height,
                                                String format, String name) throws Exception {
        Map<String, Object> body = new LinkedHashMap<>();

        boolean isSvg = looksLikeSvg(inputName, data);
        if (isSvg) {
            Map<String, String> meta = svg.parse(data);
            body.put("svg", meta);
        }

        // The stored name is a plain filename (letters, digits, '.', '_', '-')
        // - it becomes the FMM STOR target and must not carry path segments
        // or control characters into the FTP command line. ImageMagick's own
        // output path is server-chosen (see ImageMagickService). (This was an
        // unsanitised name reaching both the local output path and FMM.)
        String coder = (format == null || format.isBlank()) ? "png" : format;
        String outName = (name == null || name.isBlank())
                ? "img_" + UUID.randomUUID().toString().replace("-", "") + "." + coder.toLowerCase(Locale.ROOT)
                : name;
        if (!validStoredName(outName)) {
            throw new IllegalArgumentException("invalid name (allowed: letters, digits, . _ -)");
        }

        byte[] png;
        try {
            png = magick.convert(inputName, data, width, height, format, outName);
        } catch (Exception convertEx) {
            if (isSvg) {
                body.put("stored", false);
                body.put("name", outName);
                body.put("bytes", 0);
                body.put("convertError", String.valueOf(convertEx.getMessage()));
                return body;
            }
            throw convertEx;
        }

        boolean stored = false;
        String storeError = null;
        try {
            fmm.store(outName, png);
            stored = true;
            storedFormats.put(outName, coder);
        } catch (Exception storeEx) {
            storeError = String.valueOf(storeEx.getMessage());
        }

        body.put("stored", stored);
        body.put("name", outName);
        body.put("bytes", png.length);
        if (storeError != null) {
            body.put("storeError", storeError);
        }
        return body;
    }

    private static final java.util.regex.Pattern STORED_NAME =
            java.util.regex.Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");

    private static boolean validStoredName(String name) {
        return name != null && STORED_NAME.matcher(name).matches() && !name.contains("..");
    }

    private boolean looksLikeSvg(String inputName, byte[] data) {
        if (inputName != null && inputName.toLowerCase().endsWith(".svg")) {
            return true;
        }
        int limit = Math.min(data.length, 256);
        String head = new String(data, 0, limit).trim().toLowerCase();
        return head.startsWith("<?xml") || head.startsWith("<svg") || head.startsWith("<!doctype");
    }

    @ExceptionHandler(MultipartException.class)
    public ResponseEntity<Map<String, Object>> handleMultipartException(MultipartException e) {
        return error(e);
    }

    private ResponseEntity<Map<String, Object>> error(Exception e) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("error", e.getClass().getSimpleName());
        body.put("message", String.valueOf(e.getMessage()));
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(body);
    }
}
