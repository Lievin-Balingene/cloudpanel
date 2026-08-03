import { create } from "zustand";
import { persist } from "zustand/middleware";
import { apiRequest, configureApiAuth } from "@/lib/api";
import type { User } from "@/types";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  setSession: (access: string, refresh: string, user: User) => void;
  clearSession: () => void;
  login: (email: string, password: string, otp?: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => {
      configureApiAuth(
        () => get().accessToken,
        () => get().clearSession(),
      );

      return {
        accessToken: null,
        refreshToken: null,
        user: null,
        setSession: (access, refresh, user) =>
          set({ accessToken: access, refreshToken: refresh, user }),
        clearSession: () => set({ accessToken: null, refreshToken: null, user: null }),
        login: async (email, password, otp) => {
          const data = await apiRequest<{
            tokens: {
              access: string;
              refresh: string;
              must_change_password: boolean;
            };
            user: User;
          }>("/auth/login/", {
            method: "POST",
            body: JSON.stringify({ email, password, otp: otp ?? "" }),
          });
          set({
            accessToken: data.tokens.access,
            refreshToken: data.tokens.refresh,
            user: data.user,
          });
        },
        logout: async () => {
          const refresh = get().refreshToken;
          try {
            if (refresh) {
              await apiRequest("/auth/logout/", {
                method: "POST",
                body: JSON.stringify({ refresh }),
              });
            }
          } finally {
            get().clearSession();
          }
        },
        fetchMe: async () => {
          const user = await apiRequest<User>("/auth/me/");
          set({ user });
        },
      };
    },
    { name: "vzone-auth" },
  ),
);
