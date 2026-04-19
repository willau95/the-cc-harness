import { api } from "./client";
import type { TasksResponse } from "./types";

export const tasksApi = {
  list: () => api.get<TasksResponse>("/tasks"),
};
