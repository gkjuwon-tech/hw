#!/usr/bin/env bash
# Reference fetch script used during initial asset import.
# Pulls from images.unsplash.com which serves all photos under the Unsplash
# License. See ATTRIBUTION.md for credits.
set -euo pipefail

declare -A PHOTOS=(
  [hero-factory.jpg]="photo-1567789884554-0b844b597180"
  [problem-line.jpg]="photo-1716191299980-a6e8827ba10b"
  [product-process.jpg]="photo-1567789765727-a8d6eabb37ab"
  [cloud-circuit.jpg]="photo-1684430598817-0c77ec7babfd"
  [industry-bakery.jpg]="photo-1568254183919-78a4f43a2877"
  [industry-pharma.jpg]="photo-1587854692152-cbe660dbde88"
  [industry-cosmetics.jpg]="photo-1556228720-195a672e8a03"
  [industry-textile.jpg]="photo-1741437137271-b0cc001ea10c"
  [industry-semicon.jpg]="photo-1672307613484-3254a04651fd"
  [industry-meat.jpg]="photo-1558618666-fcd25c85cd64"
  [quote-machine.jpg]="photo-1485827404703-89b55fcc595e"
  [pricing-shipping.jpg]="photo-1553413077-190dd305871c"
  [company-floor.jpg]="photo-1532187863486-abf9dbad1b69"
  # ------ direct-order product pages ------
  [shipping-port.jpg]="photo-1494412651409-8963ce7935a7"
  [cloud-operator.jpg]="photo-1581091226825-a6a2a5aee158"
  [engineering-review.jpg]="photo-1581094288338-2314dddb7ece"
)

for name in "${!PHOTOS[@]}"; do
  id="${PHOTOS[$name]}"
  url="https://images.unsplash.com/${id}?auto=format&fit=crop&w=2000&q=70"
  echo "fetching $name from $id"
  curl -sSL -o "$name" "$url"
done
