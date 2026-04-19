import { api } from "./client";
import type { EventsResponse } from "./types";

export const eventsApi = {
  list: (limit = 200) => api.get<EventsResponse>(`/events?limit=${limit}`),
};
