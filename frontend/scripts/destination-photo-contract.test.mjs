import assert from "node:assert/strict";
import test from "node:test";
import { verifyDestinationPhotos } from "./destination-photo-contract.mjs";

const signedUrl = "https://lh3.googleusercontent.com/place-photos/expired-signature";
const overview = (photos) => ({ photos, key_attractions: [] });

test("expired CDN signatures still satisfy the API contract without network access", () => {
  assert.equal(verifyDestinationPhotos(overview([signedUrl]), "production"), 1);
  assert.equal(verifyDestinationPhotos({ photos: [], key_attractions: [{ photo: signedUrl }] }, "production"), 1);
});

test("missing photos fail production but allow cache-only canary", () => {
  assert.throws(() => verifyDestinationPhotos(overview([]), "production"), /returned no photo/);
  assert.equal(verifyDestinationPhotos(overview([]), "canary"), 0);
});

test("malformed contracts and every invalid photo fail", () => {
  assert.throws(() => verifyDestinationPhotos({}, "canary"), /invalid photo contract/);
  for (const invalid of [null, 42, "", "/photo", "http://lh3.googleusercontent.com/photo", "https://lh3.googleusercontent.com.evil.example/photo", "https://user:password@lh3.googleusercontent.com/photo"]) {
    assert.throws(() => verifyDestinationPhotos(overview([signedUrl, invalid]), "production"), /photo URL/);
  }
});

test("Google photo media endpoints satisfy the contract", () => {
  assert.equal(verifyDestinationPhotos(overview([
    "https://maps.googleapis.com/maps/api/place/photo?photoreference=ref",
    "https://places.googleapis.com/v1/places/place/photos/ref/media",
  ]), "production"), 2);
});
