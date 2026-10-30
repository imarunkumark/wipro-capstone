---
name: kyc-extraction
description: Extract identity fields from a KYC document description
model: sonnet
cache: true
---
Extract {"full_name","doc_type","doc_number","expiry"} as JSON from the supplied
document text. Mask doc_number to the last 4 characters.
