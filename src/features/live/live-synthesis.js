export async function runLiveSegmentPipeline({ segmentCount, produce, consume }) {
  const deferredResults = Array.from({ length: segmentCount }, () => {
    let resolve;
    const promise = new Promise((accept) => { resolve = accept; });
    return { promise, resolve };
  });

  const generationTask = (async () => {
    const produced = [];
    try {
      for (let index = 0; index < segmentCount; index += 1) {
        const result = await produce(index);
        produced.push(result);
        deferredResults[index].resolve({ result });
      }
      return produced;
    } catch (error) {
      for (let index = produced.length; index < deferredResults.length; index += 1) {
        deferredResults[index].resolve({ error });
      }
      throw error;
    }
  })();

  const playbackTask = (async () => {
    for (let index = 0; index < deferredResults.length; index += 1) {
      const { result, error } = await deferredResults[index].promise;
      if (error) throw error;
      await consume(result, index);
    }
  })();

  const [generationOutcome, playbackOutcome] = await Promise.allSettled([
    generationTask,
    playbackTask,
  ]);
  if (generationOutcome.status === "rejected") throw generationOutcome.reason;
  if (playbackOutcome.status === "rejected") throw playbackOutcome.reason;
  return generationOutcome.value;
}
