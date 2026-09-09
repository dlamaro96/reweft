INSERT INTO loomworks.customers VALUES
  ('000041', 'Northwind Bicycle Parts', 'AE'),
  ('1042', 'Cedar Workshop Supply', 'GB');

INSERT INTO loomworks.products VALUES
  ('P-100', 'TW-100', 'Twill Fastener'),
  ('000200', 'WT-200', 'Weft Tensioner');

INSERT INTO loomworks.invoices VALUES
  (70001, 1, '000041', 'P-100', '2026-01-15', 1200.00, 50.00, 'AED'),
  (70002, 1, '1042', '000200', '2026-01-18', 800.00, 0.00, 'AED');

INSERT INTO loomworks.monthly_adjustments VALUES ('2026-01', -75.00, 'AED');

INSERT INTO loomworks.inventory_snapshots VALUES
  ('2026-01-31', 'P-100', 'DXB', 90.000),
  ('2026-02-28', 'P-100', 'DXB', 82.000);

INSERT INTO loomworks.current_orders VALUES (81001, '2026-02-28T08:00:00Z', 'fulfilled');

