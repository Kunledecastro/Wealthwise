import { z } from "zod";

// Mirrors the server rules for fast feedback; the server remains the authority.
export const PASSWORD_MIN = 10;

export const passwordSchema = z
  .string()
  .min(PASSWORD_MIN, `Use at least ${PASSWORD_MIN} characters.`)
  .max(128, "Use at most 128 characters.");

export const loginSchema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});

export const registerSchema = z
  .object({
    display_name: z.string().trim().min(1, "Enter your name.").max(80),
    email: z.email("Enter a valid email address."),
    password: passwordSchema,
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });

export const forgotSchema = z.object({ email: z.email("Enter a valid email address.") });

export const resetSchema = z
  .object({ password: passwordSchema, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });

export const changePasswordSchema = z
  .object({ current_password: z.string().min(1, "Enter your current password."), password: passwordSchema, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });

/** Reads `key` from a URL fragment like "#invite=abc". Fragments never reach the server. */
export function fragmentParam(hash: string, key: string): string | null {
  const params = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
  const v = params.get(key);
  return v && v.length >= 20 ? v : null;
}
