"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";
import { AuthLayout } from "@/components/auth-layout";
import { useAuth } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { useFragmentToken } from "@/lib/use-fragment-token";
import { api, ApiError } from "@/lib/api";
import { PASSWORD_MIN, resetSchema } from "@/lib/schemas";

type Values = z.infer<typeof resetSchema>;

function ResetPasswordPage() {
  const { setMe } = useAuth();
  const token = useFragmentToken("token");
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<Values>({ resolver: zodResolver(resetSchema) });

  async function onSubmit(values: Values) {
    setError(null);
    try {
      const res = await api<{ message: string }>("/api/auth/password/reset", { method: "POST", body: { token, new_password: values.password } });
      setMe(null);
      setDone(res.message);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Reset failed.");
    }
  }

  return (
    <AuthLayout title="Choose a new password" footer={<Link href="/login" className="text-[var(--accent)] hover:underline">Back to sign in</Link>}>
      {done ? (
        <div className="space-y-4">
          <Alert kind="success">{done}</Alert>
          <Link href="/login" className="block text-center text-sm font-medium text-[var(--accent)] hover:underline">Go to sign in</Link>
        </div>
      ) : token === null ? (
        <Alert kind="info">This link is incomplete. <Link href="/forgot-password" className="underline">Request a new reset link.</Link></Alert>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {error && <Alert>{error}</Alert>}
          <Field label="New password" type="password" autoComplete="new-password" autoFocus hint={`At least ${PASSWORD_MIN} characters.`} error={formState.errors.password?.message} {...register("password")} />
          <Field label="Confirm new password" type="password" autoComplete="new-password" error={formState.errors.confirm?.message} {...register("confirm")} />
          <Button type="submit" size="full" loading={formState.isSubmitting}>Update password</Button>
        </form>
      )}
    </AuthLayout>
  );
}

// Client-only: the token is read from window.location, which doesn't exist on the server.
export default dynamic(() => Promise.resolve(ResetPasswordPage), { ssr: false });
