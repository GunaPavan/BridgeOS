import { SignupForm } from "@/components/ui/signup-form";

export default function SignupPatientPage() {
  return (
    <SignupForm
      role="patient"
      accentClass="text-white"
      title="Sign up as caregiver"
      blurb="Your coordinator will link your account to your patient record. After that you'll see your bridge, transfusion schedule, and current outreach status."
    />
  );
}
