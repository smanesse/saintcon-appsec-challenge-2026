package com.saintcon.ipm;

import org.springframework.stereotype.Service;
import org.w3c.dom.Document;
import org.w3c.dom.Element;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Service
public class SvgMetadataService {

    public Map<String, String> parse(byte[] svg) throws Exception {
        // External entities and external DTDs are never resolved, so an SVG
        // can't pull host files or URLs into the parse. (#6 was a default
        // DocumentBuilderFactory that resolved SYSTEM entities.)
        //
        // VULN (billion-laughs / entity-expansion DoS, #7): DOCTYPEs are still
        // accepted and internal entities are expanded with no limit (the JVM's
        // entity caps are lifted in the Dockerfile's JAVA_TOOL_OPTIONS), so
        // deeply-nested internal entities exhaust memory/CPU.
        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.setFeature("http://xml.org/sax/features/external-general-entities", false);
        dbf.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        dbf.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
        dbf.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        dbf.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        dbf.setXIncludeAware(false);
        dbf.setExpandEntityReferences(false);
        DocumentBuilder builder = dbf.newDocumentBuilder();

        Document doc = builder.parse(new ByteArrayInputStream(svg));
        Element root = doc.getDocumentElement();

        // Refuse an oversized declared canvas before ImageMagick (and its SVG
        // delegate) ever rasterises it: rendering cost scales with the
        // declared size, not the file size. (#3: a few hundred bytes declaring
        // 50000x50000 pinned a CPU per request.)
        checkDeclaredSize(root);

        Map<String, String> meta = new LinkedHashMap<>();
        meta.put("root", root.getNodeName());
        meta.put("width", root.getAttribute("width"));
        meta.put("height", root.getAttribute("height"));
        meta.put("text", root.getTextContent());
        return meta;
    }

    /** Largest declared SVG width/height (in CSS px) we will render. */
    static final double MAX_SVG_DIMENSION = 8192;

    private static void checkDeclaredSize(Element root) throws IOException {
        double w = toPixels(root.getAttribute("width"));
        double h = toPixels(root.getAttribute("height"));
        String[] vb = root.getAttribute("viewBox").trim().split("[\\s,]+");
        if (vb.length == 4) {
            if (Double.isNaN(w)) w = toPixels(vb[2]);
            if (Double.isNaN(h)) h = toPixels(vb[3]);
        }
        if (w > MAX_SVG_DIMENSION || h > MAX_SVG_DIMENSION
                || Double.isInfinite(w) || Double.isInfinite(h)) {
            throw new IOException("declared SVG canvas exceeds " + (int) MAX_SVG_DIMENSION + "px");
        }
    }

    /** A length attribute in CSS px, or NaN if absent/relative/unparseable. */
    static double toPixels(String v) {
        if (v == null) return Double.NaN;
        Matcher m = LENGTH.matcher(v.trim().toLowerCase(Locale.ROOT));
        if (!m.matches()) return Double.NaN;
        double n = Double.parseDouble(m.group(1));
        String unit = m.group(2) == null ? "" : m.group(2);
        return switch (unit) {
            case "", "px" -> n;
            case "pt" -> n * 4.0 / 3.0;
            case "pc" -> n * 16;
            case "mm" -> n * 96 / 25.4;
            case "cm" -> n * 96 / 2.54;
            case "in" -> n * 96;
            case "em", "ex" -> n * 16;
            default -> Double.NaN; // "%" is relative to a viewport we choose
        };
    }

    private static final Pattern LENGTH =
            Pattern.compile("([+-]?(?:\\d+\\.?\\d*|\\.\\d+)(?:e[+-]?\\d+)?)\\s*(px|pt|pc|mm|cm|in|em|ex|%)?");
}
