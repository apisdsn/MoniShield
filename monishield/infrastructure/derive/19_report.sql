-- agg_report: PDF generation per template (the report service); failed = 'Jasper template path : null'.
DELETE FROM agg_report WHERE folder = $f;
INSERT INTO agg_report
SELECT $f, pdf_template, count(*) FILTER (WHERE NOT pdf_failed), count(*) FILTER (WHERE pdf_failed)
FROM spring_line WHERE folder = $f AND service = $rp AND pdf_template IS NOT NULL GROUP BY pdf_template;
