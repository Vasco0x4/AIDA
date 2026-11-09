// Database timestamps without an offset are UTC. Preserve explicit offsets,
// date-only values and native Date constructor arguments.
export function utcDate(...args) {
  if (args.length === 1 && typeof args[0] === 'string' &&
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(args[0])) {
    return new Date(`${args[0]}Z`);
  }
  return new Date(...args);
}
