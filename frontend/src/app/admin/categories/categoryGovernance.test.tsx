import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { CategoryForm, EMPTY_CATEGORY_FORM, type CategoryFormValues } from "./categoryGovernance";

vi.mock("next/link", () => import("@/test/next-link"));

function Harness() {
  const [values, setValues] = useState<CategoryFormValues>(EMPTY_CATEGORY_FORM);
  return (
    <CategoryForm
      values={values}
      onChange={setValues}
      onSubmit={() => {}}
      onCancel={() => {}}
      submitting={false}
      submitLabel="Create Category"
      error={null}
      autoSlug
      idPrefix="test"
    />
  );
}

const name = () => screen.getByLabelText(/Name/) as HTMLInputElement;
const slug = () => screen.getByLabelText(/Slug/) as HTMLInputElement;

describe("CategoryForm slug (BUG-105)", () => {
  it("follows the name until edited, then keeps the hand-typed slug", () => {
    render(<Harness />);
    fireEvent.change(name(), { target: { value: "Mens Wear" } });
    expect(slug()).toHaveValue("mens-wear");

    fireEvent.change(slug(), { target: { value: "men" } });
    fireEvent.change(name(), { target: { value: "Mens Wear & Bags" } });
    expect(slug()).toHaveValue("men");

    // Clearing the slug hands it back to the name.
    fireEvent.change(slug(), { target: { value: "" } });
    fireEvent.change(name(), { target: { value: "Bags" } });
    expect(slug()).toHaveValue("bags");
  });

  it("explains an empty slug for a name with no URL letters", () => {
    render(<Harness />);
    fireEvent.change(name(), { target: { value: "পোশাক" } });
    expect(slug()).toHaveValue("");
    expect(screen.getByText(/type a slug/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Category" })).toBeDisabled();
  });
});
