import type { Summary } from "./types";

const SUMMARY_URL = "/api/summary";

const REQUEST_TIMEOUT_MS = 8000;

export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function fetchSummary(signal?: AbortSignal): Promise<Summary> {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;

  let response: Response;
  try {
    response = await fetch(SUMMARY_URL, {
      signal: combined,
      headers: { Accept: "application/json" },
    });
  } catch (cause) {
    if (signal?.aborted) throw cause;
    throw new ApiError(
      "Cannot reach the dashboard API. In development this usually means the " +
        "SSH tunnel on port 8000 is not open.",
    );
  }

  if (!response.ok) {
    throw new ApiError(`The API returned ${response.status}.`, response.status);
  }

  return (await response.json()) as Summary;
}
