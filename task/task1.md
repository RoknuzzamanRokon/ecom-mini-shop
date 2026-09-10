Using the MiniShop Master Prompt and the existing project files, perform a complete architecture audit.

DO NOT implement new features yet.

Analyze the existing Django REST Framework backend and Next.js frontend.

Check:

1. Django project structure
2. Django apps
3. Existing User model
4. Authentication
5. JWT implementation
6. Existing Product model
7. Existing Category model
8. Existing Order/cart implementation
9. Existing serializers
10. Existing API views/viewsets
11. Existing URL routing
12. Existing permissions
13. Existing frontend structure
14. Existing API client
15. Authentication state management
16. Existing admin dashboard
17. Existing reusable components
18. Existing database configuration
19. Existing media/image handling
20. Existing testing setup

Then provide:

A. Current architecture diagram

B. Existing models and relationships

C. Existing API endpoints

D. Existing frontend routes

E. What should be kept

F. What should be refactored

G. What is missing for the MiniShop architecture

H. Security problems

I. Scalability problems

J. Recommended development order

IMPORTANT:

Do not rewrite anything.

Do not generate a new project.

Do not implement future features.

Only analyze the existing project and produce a concrete technical roadmap based on the actual code.


IMPORTANT AUDIT REQUIREMENT:

Base every finding on the actual existing project code.

Do not give generic Django or Next.js recommendations without checking the project.

Whenever possible, mention:
- exact file path
- app/module name
- model name
- serializer name
- view/viewset name
- API endpoint
- frontend route
- component name

For every problem, explain:
1. Current implementation
2. Why it is a problem
3. Recommended improvement
4. Whether it must be fixed now or can be postponed

Clearly separate:
- Critical issues
- Important issues
- Nice-to-have improvements

Do not modify any file.
Do not create any file.
Do not generate implementation code unless a tiny code snippet is necessary to explain an architectural problem.