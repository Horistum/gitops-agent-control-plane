# Security model

V7 separates core autonomy from verification security. `standalone-local/v2` is **not a security sandbox**. JUnit is not authoritative. The property-probe parent receipt is authoritative only inside deterministic fixture scope. Current final-receipt injection is blocked; raw-outcome forgery remains executable KNOWN-LIMIT. The event chain is **not an authenticity mechanism** without an external anchor. Production hostile code requires stronger isolated verification.
