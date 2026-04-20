import { api } from "./client";

export interface ParentDirsResponse {
  machine: string;
  home: string;
  parents: { path: string; display: string }[];
}

export const fsApi = {
  parentDirs: (machine?: string) =>
    api.get<ParentDirsResponse>(
      `/fs/parent-dirs${machine && machine !== "__local__" ? `?machine=${encodeURIComponent(machine)}` : ""}`,
    ),
};
