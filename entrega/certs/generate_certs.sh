#!/bin/bash
set -e

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$CERT_DIR/key.pem" \
  -out "$CERT_DIR/cert.pem" \
  -days 365 \
  -subj "/CN=pizzaria-online" \
  -addext "subjectAltName=DNS:localhost,DNS:gateway,DNS:users,DNS:products-1,DNS:products-2,DNS:orders,IP:127.0.0.1"

echo "Certificado gerado em: $CERT_DIR/cert.pem"
echo "Chave privada gerada em: $CERT_DIR/key.pem"
