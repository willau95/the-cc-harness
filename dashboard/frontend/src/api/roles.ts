import { api } from "./client";
import type { RolesResponse } from "./types";

export const rolesApi = {
  list: () => api.get<RolesResponse>("/roles"),
};
