import { api } from "./client";
import type { MachinesResponse } from "./types";

export const machinesApi = {
  list: () => api.get<MachinesResponse>("/machines"),
};
