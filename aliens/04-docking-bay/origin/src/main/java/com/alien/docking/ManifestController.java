package com.alien.docking;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.xml.sax.InputSource;

import javax.xml.parsers.DocumentBuilderFactory;
import java.io.ByteArrayInputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputStream;
import java.io.StringReader;
import java.util.Base64;

/**
 * Docking-manifest backup/restore and schema-validation tooling.
 */
@RestController
public class ManifestController {

    /** Restore a manifest from a base64-encoded serialized backup. */
    @PostMapping(value = "/dock/import", produces = MediaType.TEXT_PLAIN_VALUE)
    public String importManifest(@RequestBody(required = false) String body, HttpServletResponse resp) {
        if (body == null || body.isBlank()) {
            resp.setStatus(400);
            return "no manifest payload\n";
        }
        byte[] raw;
        try {
            raw = Base64.getDecoder().decode(body.trim());
        } catch (IllegalArgumentException e) {
            resp.setStatus(400);
            return "manifest payload must be base64\n";
        }
        try (ObjectInputStream ois = new SafeObjectInputStream(new ByteArrayInputStream(raw))) {
            Object restored = ois.readObject();
            return "manifest restored: " + restored + "\n";
        } catch (InvalidClassException e) {
            resp.setStatus(400);
            return "manifest import rejected: " + e.getMessage() + "\n";
        } catch (Exception e) {
            resp.setStatus(400);
            return "corrupt manifest stream: " + e.getClass().getSimpleName() + "\n";
        }
    }

    /** Validate an XML manifest against the bay schema. */
    @PostMapping(value = "/manifest/validate",
            consumes = {MediaType.APPLICATION_XML_VALUE, MediaType.TEXT_XML_VALUE, MediaType.TEXT_PLAIN_VALUE},
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String validate(@RequestBody(required = false) String xml, HttpServletResponse resp) {
        if (xml == null || xml.isBlank()) {
            resp.setStatus(400);
            return "empty manifest\n";
        }
        try {
            DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
            f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            f.setFeature("http://xml.org/sax/features/external-general-entities", false);
            f.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            f.setXIncludeAware(false);
            f.setExpandEntityReferences(false);
            var doc = f.newDocumentBuilder().parse(new InputSource(new StringReader(xml)));
            return "manifest OK: root element <" + doc.getDocumentElement().getNodeName() + ">\n";
        } catch (Exception e) {
            resp.setStatus(400);
            return "manifest validation failed: " + e.getMessage() + "\n";
        }
    }
}
