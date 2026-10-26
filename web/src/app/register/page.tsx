"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
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
import { api, ApiError, type Me } from "@/lib/api";
import { PASSWORD_MIN, registerSchema } from "@/lib/schemas";

type Values = z.infer<typeof registerSchema>;

function RegisterPage() {
  const router = useRouter();
  const { setMe } = useAuth();
  const invite = useFragmentToken("invite");
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState, setError: setFieldError } = useForm<Values>({ resolver: zodResolver(registerSchema) });

  async function onSubmit(values: Values) {
    setError(null);
    try {
      const me = await api<Me>("/api/auth/register", {
        method: "POST",
        body: { invite_token: invite, email: values.email, display_name: values.display_name, password: values.password },
      });
      setMe(me);
      router.replace("/");
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && /password/i.test(e.message)) {
        setFieldError("password", { message: e.message });
      } else {
        setError(e instanceof ApiError ? e.message : "Registration failed.");
      }
    }
  }

  if (invite === null) {
    return (
      <AuthLayout title="Invite required" footer={<Link href="/login" className="text-[var(--accent)] hover:underline">Back to sign in</Link>}>
        <Alert kind="info">This app is invite-only. Open the full invite link your administrator sent you, or ask them for a new one.</Alert>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Create your account" subtitle="You've been invited. Set up your login below." footer={<>Already have an account? <Link href="/login" className="text-[var(--accent)] hover:underline">Sign in</Link></>}>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {error && <Alert>{error}</Alert>}
        <Field label="Your name" autoComplete="name" autoFocus error={formState.errors.display_name?.message} {...register("display_name")} />
        <Field label="Email" type="email" autoComplete="email" inputMode="email" error={formState.errors.email?.message} {...register("email")} />
        <Field label="Password" type="password" autoComplete="new-password" hint={`At least ${PASSWORD_MIN} characters. A short phrase works well.`} error={formState.errors.password?.message} {...register("password")} />
        <Field label="Confirm password" type="password" autoComplete="new-password" error={formState.errors.confirm?.message} {...register("confirm")} />
        <Button type="submit" size="full" loading={formState.isSubmitting}>Create account</Button>
      </form>
    </AuthLayout>
  );
}

// Client-only: the token is read from window.location, which doesn't exist on the server.
export default dynamic(() => Promise.resolve(RegisterPage), { ssr: false });
