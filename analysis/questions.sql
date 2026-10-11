SELECT category,verdict,COUNT(*) checks,COUNT(DISTINCT paper) papers,1.0*COUNT(*)/SUM(COUNT(*)) OVER(PARTITION BY category) share_within_category FROM observations GROUP BY category,verdict ORDER BY category,verdict;
SELECT paper,COUNT(*) checks,SUM(verdict='verified') verified FROM observations GROUP BY paper ORDER BY checks DESC,paper;
