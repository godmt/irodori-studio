import assert from "node:assert/strict";
import test from "node:test";

import { getTrainingVramWarning } from "../src/features/training/training-requirements.js";

const recommendations = {
  speaker_inversion: { bf16: 12, fp16: 12, fp32: 16 },
  lora: { bf16: 24, fp16: 24, fp32: 32 },
};

test("LoRA warns when total CUDA VRAM is below the selected precision recommendation", () => {
  assert.deepEqual(getTrainingVramWarning({
    method: "lora",
    device: "cuda",
    precision: "bf16",
    totalVramGb: 12,
    recommendedVramGb: recommendations,
  }), {
    method: "lora",
    totalVramGb: 12,
    recommendedVramGb: 24,
  });
});

test("LoRA does not warn when CUDA VRAM meets the recommendation", () => {
  assert.equal(getTrainingVramWarning({
    method: "lora",
    device: "cuda",
    precision: "fp32",
    totalVramGb: 32,
    recommendedVramGb: recommendations,
  }), null);
});

test("Speaker Inversion warns below its smaller recommendation", () => {
  assert.deepEqual(getTrainingVramWarning({
    method: "speaker_inversion",
    device: "cuda",
    precision: "bf16",
    totalVramGb: 8,
    recommendedVramGb: recommendations,
  }), {
    method: "speaker_inversion",
    totalVramGb: 8,
    recommendedVramGb: 12,
  });
});

test("Nominal 12 GB cards satisfy the Speaker Inversion recommendation", () => {
  assert.equal(getTrainingVramWarning({
    method: "speaker_inversion",
    device: "cuda",
    precision: "bf16",
    totalVramGb: 11.99,
    recommendedVramGb: recommendations,
  }), null);
});

test("CPU training does not use the VRAM warning", () => {
  assert.equal(getTrainingVramWarning({
    method: "lora",
    device: "cpu",
    precision: "fp32",
    totalVramGb: 0,
    recommendedVramGb: recommendations,
  }), null);
});
