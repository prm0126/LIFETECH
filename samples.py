"""
Bundled sample reports that can be loaded into Custom Reports with one click.

All queries are read-only SELECTs, filter ISVALID = 1 on every table, and use
the interactive parameters :date_from / :date_to / :gran where useful. Amounts
use NET_AMOUNT. INV/PH billing rows have no own date, so they join
GEN_PAT_BILLING for BILL_DATE.
"""

BILLING_REPORTS = [
    {
        "title": "Billing Revenue Trend",
        "type": "line",
        "sql": """
SELECT TO_CHAR(TRUNC(BILL_DATE, :gran), 'YYYY-MM-DD') AS period,
       ROUND(SUM(NET_AMOUNT), 2)                      AS net_amount
FROM   GEN_PAT_BILLING
WHERE  ISVALID = 1
  AND  BILL_DATE >= :date_from AND BILL_DATE < :date_to + 1
GROUP BY TRUNC(BILL_DATE, :gran)
ORDER BY 1
""".strip(),
    },
    {
        "title": "Revenue by Source",
        "type": "bar",
        "sql": """
SELECT 'Services' AS source, ROUND(SUM(i.NET_AMOUNT), 2) AS net_amount
FROM   INV_PAT_BILLING i
JOIN   GEN_PAT_BILLING g ON g.GEN_PAT_BILLING_ID = i.GEN_PAT_BILLING_ID
WHERE  i.ISVALID = 1 AND g.ISVALID = 1
  AND  g.BILL_DATE >= :date_from AND g.BILL_DATE < :date_to + 1
UNION ALL
SELECT 'Pharmacy', ROUND(SUM(p.NET_AMOUNT), 2)
FROM   PH_PAT_BILLING p
JOIN   GEN_PAT_BILLING g ON g.GEN_PAT_BILLING_ID = p.GEN_PAT_BILLING_ID
WHERE  p.ISVALID = 1 AND g.ISVALID = 1
  AND  g.BILL_DATE >= :date_from AND g.BILL_DATE < :date_to + 1
UNION ALL
SELECT 'Consultation', ROUND(SUM(c.NET_AMOUNT), 2)
FROM   CON_PAT_BILLING c
WHERE  c.ISVALID = 1
  AND  c.BILL_DATE >= :date_from AND c.BILL_DATE < :date_to + 1
""".strip(),
    },
    {
        "title": "Top 20 Services by Revenue",
        "type": "bar",
        "sql": """
SELECT service, net_amount FROM (
  SELECT s.NAME AS service, ROUND(SUM(i.NET_AMOUNT), 2) AS net_amount
  FROM   INV_PAT_BILLING i
  JOIN   GEN_PAT_BILLING g ON g.GEN_PAT_BILLING_ID = i.GEN_PAT_BILLING_ID
  JOIN   INV_MAST_SERVICE s ON s.INV_MAST_SERVICE_ID = i.INV_MAST_SERVICE_ID
  WHERE  i.ISVALID = 1 AND g.ISVALID = 1 AND s.ISVALID = 1
    AND  g.BILL_DATE >= :date_from AND g.BILL_DATE < :date_to + 1
  GROUP BY s.NAME
  ORDER BY net_amount DESC
) WHERE ROWNUM <= 20
""".strip(),
    },
    {
        "title": "Top 20 Pharmacy Items by Revenue",
        "type": "bar",
        "sql": """
SELECT item, net_amount FROM (
  SELECT s.NAME AS item, ROUND(SUM(p.NET_AMOUNT), 2) AS net_amount
  FROM   PH_PAT_BILLING p
  JOIN   GEN_PAT_BILLING g ON g.GEN_PAT_BILLING_ID = p.GEN_PAT_BILLING_ID
  JOIN   INV_MAST_SERVICE s ON s.INV_MAST_SERVICE_ID = p.INV_MAST_SERVICE_ID
  WHERE  p.ISVALID = 1 AND g.ISVALID = 1 AND s.ISVALID = 1
    AND  g.BILL_DATE >= :date_from AND g.BILL_DATE < :date_to + 1
  GROUP BY s.NAME
  ORDER BY net_amount DESC
) WHERE ROWNUM <= 20
""".strip(),
    },
    {
        "title": "Consultation Revenue by Provider",
        "type": "bar",
        "sql": """
SELECT NVL(GET_EMPLOYEE_NAME(provider_id), provider_id) AS provider, net_amount
FROM (
  SELECT PROVIDER_ID AS provider_id, ROUND(SUM(NET_AMOUNT), 2) AS net_amount
  FROM   CON_PAT_BILLING
  WHERE  ISVALID = 1
    AND  BILL_DATE >= :date_from AND BILL_DATE < :date_to + 1
  GROUP BY PROVIDER_ID
)
ORDER BY net_amount DESC
""".strip(),
    },
    {
        "title": "Pharmacy Revenue Trend",
        "type": "line",
        "sql": """
SELECT TO_CHAR(TRUNC(g.BILL_DATE, :gran), 'YYYY-MM-DD') AS period,
       ROUND(SUM(p.NET_AMOUNT), 2)                      AS pharmacy_net
FROM   PH_PAT_BILLING p
JOIN   GEN_PAT_BILLING g ON g.GEN_PAT_BILLING_ID = p.GEN_PAT_BILLING_ID
WHERE  p.ISVALID = 1 AND g.ISVALID = 1
  AND  g.BILL_DATE >= :date_from AND g.BILL_DATE < :date_to + 1
GROUP BY TRUNC(g.BILL_DATE, :gran)
ORDER BY 1
""".strip(),
    },
    {
        "title": "Discount Given Trend",
        "type": "line",
        "sql": """
SELECT TO_CHAR(TRUNC(BILL_DATE, :gran), 'YYYY-MM-DD') AS period,
       ROUND(SUM(DISCOUNT), 2)                        AS discount
FROM   GEN_PAT_BILLING
WHERE  ISVALID = 1
  AND  BILL_DATE >= :date_from AND BILL_DATE < :date_to + 1
GROUP BY TRUNC(BILL_DATE, :gran)
ORDER BY 1
""".strip(),
    },
    {
        "title": "Revenue Today (Net)",
        "type": "card",
        "sql": """
SELECT ROUND(SUM(NET_AMOUNT), 2) AS revenue_today
FROM   GEN_PAT_BILLING
WHERE  ISVALID = 1 AND TRUNC(BILL_DATE) = TRUNC(SYSDATE)
""".strip(),
    },
]
