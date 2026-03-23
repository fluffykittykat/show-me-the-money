import subprocess
import logging

logger = logging.getLogger(__name__)


class BriefingGenerator:
    """Generates an AI briefing using the claude CLI subprocess."""

    async def generate(self, congress_data: dict, fec_data: dict, efd_data: dict) -> str:
        """Generate an FBI-style political intelligence briefing from aggregated data.

        Args:
            congress_data: Data from Congress API (member info, bills, committees).
            fec_data: Data from FEC API (contributors, totals, PAC contributions).
            efd_data: Data from EFD filings (assets, votes).

        Returns:
            The generated briefing text.
        """
        prompt_text = self._build_prompt(congress_data, fec_data, efd_data)

        try:
            result = subprocess.run(
                ["claude", "-p", "--dangerously-skip-permissions", prompt_text],
                capture_output=True,
                text=True,
                timeout=180,
            )

            if result.returncode != 0:
                logger.warning(
                    "claude CLI returned non-zero exit code %d: %s",
                    result.returncode,
                    result.stderr,
                )
                briefing = self._build_fallback_briefing(congress_data, fec_data, efd_data)
            else:
                briefing = result.stdout.strip()

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.error("Failed to run claude CLI: %s", exc)
            briefing = self._build_fallback_briefing(congress_data, fec_data, efd_data)

        with open("/tmp/briefing.txt", "w") as f:
            f.write(briefing)

        return briefing

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, congress_data: dict, fec_data: dict, efd_data: dict) -> str:
        sections: list[str] = []

        # --- Member info ---
        member = congress_data.get("member", {})
        name = member.get("directOrderName", member.get("name", "Unknown"))
        party = member.get("partyName", member.get("party", "Unknown"))
        state = member.get("state", "Unknown")
        committees = congress_data.get("committees", member.get("committees", []))
        comm_names = [c.get("name", c) if isinstance(c, dict) else c for c in committees]
        sections.append(
            f"MEMBER: {name}\nParty: {party}\nState: {state}\n"
            f"Committees: {', '.join(comm_names) if comm_names else 'N/A'}"
        )

        # --- Top donors ---
        top_contributors = fec_data.get("top_contributors", [])
        if top_contributors:
            donor_lines = []
            for donor in top_contributors[:10]:
                donor_name = donor.get("contributor_name", donor.get("name", "Unknown"))
                amount = donor.get("contribution_receipt_amount", donor.get("amount", 0)) or 0
                employer = donor.get("contributor_employer", donor.get("employer", "N/A"))
                occupation = donor.get("contributor_occupation", donor.get("occupation", "N/A"))
                donor_lines.append(
                    f"  - {donor_name}: ${amount:,.2f} (Employer: {employer}, Occupation: {occupation})"
                )
            sections.append("TOP DONORS:\n" + "\n".join(donor_lines))

        # --- Campaign totals ---
        totals = fec_data.get("totals", {})
        if totals:
            total_raised = totals.get("receipts", totals.get("total_raised", 0)) or 0
            total_spent = totals.get("disbursements", totals.get("total_spent", 0)) or 0
            sections.append(
                f"CAMPAIGN TOTALS:\n  Total Raised: ${total_raised:,.2f}\n  Total Spent: ${total_spent:,.2f}"
            )

        # --- PAC contributions ---
        pac_contributions = fec_data.get("pac_contributions", [])
        if pac_contributions:
            pac_lines = [
                f"  - {pac.get('contributor_name', pac.get('name', 'Unknown'))}: "
                f"${(pac.get('contribution_receipt_amount', pac.get('amount', 0)) or 0):,.2f}"
                for pac in pac_contributions[:10]
            ]
            sections.append("TOP PAC CONTRIBUTIONS:\n" + "\n".join(pac_lines))

        # --- Sponsored bills ---
        sponsored_bills = congress_data.get("sponsored_bills", [])
        if sponsored_bills:
            bill_lines = [f"  - {bill.get('title', 'Untitled')}" for bill in sponsored_bills]
            sections.append("SPONSORED BILLS:\n" + "\n".join(bill_lines))

        # --- Committee assignments ---
        committee_data = congress_data.get("committees", [])
        if committee_data:
            comm_lines = [f"  - {c}" if isinstance(c, str) else f"  - {c.get('name', 'Unknown')}" for c in committee_data]
            sections.append("COMMITTEE ASSIGNMENTS:\n" + "\n".join(comm_lines))

        # --- Financial assets ---
        assets = efd_data.get("assets", [])
        if assets:
            asset_lines = [
                f"  - {a.get('name', 'Unknown')}: {a.get('value', 'N/A')}"
                for a in assets
            ]
            sections.append("FINANCIAL ASSETS:\n" + "\n".join(asset_lines))

        # --- Recent votes ---
        votes = efd_data.get("votes", [])
        if votes:
            vote_lines = [
                f"  - {v.get('question', v.get('description', 'Unknown'))}: "
                f"{v.get('result', v.get('position', 'N/A'))} "
                f"(Date: {v.get('date', 'N/A')})"
                for v in votes[:15]
            ]
            sections.append("RECENT VOTES:\n" + "\n".join(vote_lines))

        data_block = "\n\n".join(sections)

        prompt = (
            "You are a senior political intelligence analyst. Using ONLY the data provided below, "
            "write a 4-paragraph FBI-style political intelligence briefing on this member of Congress.\n\n"
            "DATA:\n"
            f"{data_block}\n\n"
            "STRUCTURE:\n"
            "Paragraph 1: Overview and role - who they are, party, state, committee assignments.\n"
            "Paragraph 2: Financial interests and potential conflicts of interest between "
            "personal assets and legislative duties.\n"
            "Paragraph 3: Campaign finance and donor analysis - total raised/spent, top donors, "
            "PAC contributions, and alignment between donor industries and committee assignments.\n"
            "Paragraph 4: Legislative record and voting patterns - sponsored bills, recent votes, "
            "and any notable patterns.\n\n"
            "GUIDELINES:\n"
            "- Be factual and cite specific numbers from the data.\n"
            "- Note any conflicts of interest between financial holdings and committee assignments.\n"
            "- Note alignment or misalignment between top donor industries and committee assignments.\n"
            "- Write in present tense.\n"
            "- Do NOT speculate beyond the provided data."
        )

        return prompt

    # ------------------------------------------------------------------
    # Fallback briefing when the CLI is unavailable
    # ------------------------------------------------------------------

    def _build_fallback_briefing(
        self, congress_data: dict, fec_data: dict, efd_data: dict
    ) -> str:
        member = congress_data.get("member", {})
        name = member.get("directOrderName", member.get("name", "Unknown"))
        party = member.get("partyName", member.get("party", "Unknown"))
        state = member.get("state", "Unknown")
        committees = congress_data.get("committees", member.get("committees", []))

        totals = fec_data.get("totals", {})
        total_raised = totals.get("receipts", totals.get("total_raised", 0)) or 0
        total_spent = totals.get("disbursements", totals.get("total_spent", 0)) or 0

        top_contributors = fec_data.get("top_contributors", [])
        pac_contributions = fec_data.get("pac_contributions", [])
        sponsored_bills = congress_data.get("sponsored_bills", [])
        assets = efd_data.get("assets", [])
        votes = efd_data.get("votes", [])

        # Paragraph 1 - Overview
        comm_names = [c.get("name", c) if isinstance(c, dict) else c for c in committees]
        committee_str = ", ".join(comm_names) if comm_names else "no listed committees"
        para1 = (
            f"{name} ({party}-{state}) currently serves in Congress with assignments on {committee_str}."
        )

        # Paragraph 2 - Financial interests
        if assets:
            asset_summary = "; ".join(
                f"{a.get('name', 'Unknown')} ({a.get('value', 'N/A')})" for a in assets[:5]
            )
            para2 = f"Reported financial assets include: {asset_summary}."
        else:
            para2 = "No financial asset disclosures are available for this member."

        # Paragraph 3 - Campaign finance
        donor_summary = ""
        if top_contributors:
            top_names = ", ".join(
                d.get("contributor_name", d.get("name", "Unknown")) for d in top_contributors[:5]
            )
            donor_summary = f" Top individual donors include {top_names}."
        pac_summary = ""
        if pac_contributions:
            top_pacs = ", ".join(
                p.get("contributor_name", p.get("name", "Unknown")) for p in pac_contributions[:5]
            )
            pac_summary = f" Leading PAC contributors include {top_pacs}."
        para3 = (
            f"Campaign finance records show ${total_raised:,.2f} raised and ${total_spent:,.2f} spent."
            f"{donor_summary}{pac_summary}"
        )

        # Paragraph 4 - Legislative record
        if sponsored_bills:
            bill_titles = "; ".join(b.get("title", "Untitled") for b in sponsored_bills[:5])
            para4 = f"Sponsored legislation includes: {bill_titles}."
        else:
            para4 = "No sponsored legislation is recorded in the available data."
        if votes:
            vote_summary = "; ".join(
                f"{v.get('description', 'Unknown')} ({v.get('position', 'N/A')})"
                for v in votes[:5]
            )
            para4 += f" Recent voting record: {vote_summary}."

        return f"{para1}\n\n{para2}\n\n{para3}\n\n{para4}"
