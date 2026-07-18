export type SystemPromptModules = Record<string, Record<string, Record<string, string>>>;

export function createSystemPromptCache(loader: () => Promise<SystemPromptModules>) {
  let cached: SystemPromptModules | null = null;
  let inFlight: Promise<SystemPromptModules> | null = null;
  let generation = 0;

  return {
    load() {
      if (cached) return Promise.resolve(cached);
      if (inFlight) return inFlight;

      const loadGeneration = generation;
      const request = loader()
        .then((value) => {
          if (loadGeneration === generation) cached = value;
          return value;
        })
        .finally(() => {
          if (inFlight === request) inFlight = null;
        });
      inFlight = request;
      return inFlight;
    },
    clear() {
      generation += 1;
      cached = null;
      inFlight = null;
    },
  };
}
