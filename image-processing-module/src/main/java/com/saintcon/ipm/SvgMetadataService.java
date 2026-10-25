package com.saintcon.ipm;

import org.springframework.stereotype.Service;
import org.w3c.dom.Document;
import org.w3c.dom.Element;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.ByteArrayInputStream;
import java.util.LinkedHashMap;
import java.util.Map;

@Service
public class SvgMetadataService {

    public Map<String, String> parse(byte[] svg) throws Exception {
        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        DocumentBuilder builder = dbf.newDocumentBuilder();

        Document doc = builder.parse(new ByteArrayInputStream(svg));
        Element root = doc.getDocumentElement();

        Map<String, String> meta = new LinkedHashMap<>();
        meta.put("root", root.getNodeName());
        meta.put("width", root.getAttribute("width"));
        meta.put("height", root.getAttribute("height"));
        meta.put("text", root.getTextContent());
        return meta;
    }
}
